import logging
import re
import uuid

import aiohttp
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import SubscriptionPlan
from heroes.data import get_hero
from keyboards.builders import kb_subscribe
from services.subscription_service import SubscriptionService
from services.user_service import UserService

subscription_router = Router(name="subscription")
logger = logging.getLogger(__name__)

_YUKASSA_API = "https://api.yookassa.ru/v3/payments"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PaymentStates(StatesGroup):
    waiting_email    = State()  # collect email if no phone
    waiting_city     = State()  # collect city
    waiting_district = State()  # collect district
    waiting_check    = State()  # payment link sent, waiting confirmation


# ── ЮКасса API ────────────────────────────────────────────────────────────────

def _build_receipt(contact: str, description: str, amount_kopecks: int) -> dict:
    """Build YuKassa receipt object (54-ФЗ). contact = phone or email."""
    customer = (
        {"phone": contact} if contact.startswith("+") or contact.isdigit()
        else {"email": contact}
    )
    return {
        "customer": customer,
        "items": [
            {
                "description": description,
                "quantity": "1.00",
                "amount": {"value": f"{amount_kopecks / 100:.2f}", "currency": "RUB"},
                "vat_code": 1,           # без НДС
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }
        ],
    }


async def _create_payment(
    amount_kopecks: int,
    description: str,
    user_id: int,
    plan: str,
    contact: str,
    city: str = "",
    district: str = "",
) -> dict:
    payload = {
        "amount": {"value": f"{amount_kopecks / 100:.2f}", "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{settings.bot_username}",
        },
        "capture": True,
        "description": description,
        "receipt": _build_receipt(contact, description, amount_kopecks),
        "metadata": {
            "user_id": str(user_id),
            "plan": plan,
            "city": city,
            "district": district,
        },
    }
    auth = aiohttp.BasicAuth(settings.yukassa_shop_id, settings.yukassa_secret_key)
    async with aiohttp.ClientSession() as http:
        async with http.post(
            _YUKASSA_API,
            json=payload,
            auth=auth,
            headers={"Idempotence-Key": str(uuid.uuid4())},
        ) as resp:
            data = await resp.json()
            logger.info("YuKassa create response (status=%s): %s", resp.status, data)
            if resp.status not in (200, 201) or "confirmation" not in data:
                raise RuntimeError(f"YuKassa error: {data.get('description', data)}")
            return data


async def _get_payment(payment_id: str) -> dict:
    auth = aiohttp.BasicAuth(settings.yukassa_shop_id, settings.yukassa_secret_key)
    async with aiohttp.ClientSession() as http:
        async with http.get(
            f"{_YUKASSA_API}/{payment_id}",
            auth=auth,
        ) as resp:
            return await resp.json()


def _kb_payment(url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Перейти к оплате", url=url)
    kb.button(text="✅ Я оплатил — проверить", callback_data="sub:check")
    kb.adjust(1)
    return kb.as_markup()


# ── Общий хелпер: создать платёж и отправить ссылку ──────────────────────────

async def _send_payment_link(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    plan    = data.get("plan", "monthly")
    contact = data.get("contact", "")
    city    = data.get("city", "")
    district = data.get("district", "")
    user_id = data.get("user_id") or message.chat.id

    if plan == "monthly":
        description = "Подписка на месяц — Habit Tracker Bot"
        amount = settings.price_monthly
        plan_label = "месяц — 249 ₽"
    else:
        description = "Подписка на год — Habit Tracker Bot"
        amount = settings.price_yearly
        plan_label = "год — 1790 ₽"

    try:
        resp = await _create_payment(amount, description, user_id, plan, contact, city, district)
        payment_id = resp["id"]
        pay_url = resp["confirmation"]["confirmation_url"]
    except Exception as e:
        logger.error("YuKassa payment creation failed user=%s: %s", user_id, e)
        await message.answer("❌ Не удалось создать ссылку на оплату. Попробуйте позже.")
        return

    await state.update_data(payment_id=payment_id)
    await state.set_state(PaymentStates.waiting_check)

    await message.answer(
        f"💳 *Подписка на {plan_label}*\n\n"
        f"Нажмите кнопку ниже, оплатите на странице ЮКассы и вернитесь обратно.\n"
        f"После оплаты нажмите *«✅ Я оплатил»* — бот проверит и активирует подписку.",
        parse_mode="Markdown",
        reply_markup=_kb_payment(pay_url),
    )


# ── /subscribe ────────────────────────────────────────────────────────────────

@subscription_router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)

    sub_svc = SubscriptionService()
    hero = get_hero(user.hero_key if user else "capybara")

    if user and sub_svc.is_subscribed(user):
        days = sub_svc.subscription_days_left(user)
        await message.answer(
            f"💳 Подписка активна. Осталось *{days} дн.*\n\nХотите продлить прямо сейчас?",
            parse_mode="Markdown",
            reply_markup=kb_subscribe(),
        )
        return

    trial_info = ""
    if user and sub_svc.is_trial(user):
        days = sub_svc.trial_days_left(user)
        trial_info = f"🕐 Бесплатный период: ещё *{days} дн.*\n\n"

    await message.answer(
        f"{hero.emoji} Выберите план подписки:\n\n"
        f"{trial_info}"
        f"💳 *Месяц* — 249 ₽\n"
        f"💎 *Год* — 1790 ₽ _(экономия 1198 ₽)_\n",
        parse_mode="Markdown",
        reply_markup=kb_subscribe(),
    )


# ── Проверить платёж (РАНЬШЕ общего sub: хендлера) ───────────────────────────

@subscription_router.callback_query(F.data == "sub:check")
async def cb_check_payment(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    payment_id: str | None = data.get("payment_id")
    plan_key: str | None = data.get("plan")

    if not payment_id:
        await callback.answer(
            "Нет активного платежа. Выберите план через /subscribe.", show_alert=True
        )
        return

    await callback.answer("Проверяем оплату…")

    try:
        resp = await _get_payment(payment_id)
        status = resp.get("status")
    except Exception as e:
        logger.error("YuKassa check failed payment=%s: %s", payment_id, e)
        await callback.message.answer("❌ Не удалось проверить платёж. Попробуйте позже.")
        return

    if status == "succeeded":
        plan = SubscriptionPlan.MONTHLY if plan_key == "monthly" else SubscriptionPlan.YEARLY
        user_svc = UserService(session)
        sub_svc = SubscriptionService()
        user = await user_svc.get_or_raise(callback.from_user.id)
        new_expiry = sub_svc.activate(user, plan)
        await user_svc.update(user, subscription_plan=plan, subscription_expires_at=new_expiry)

        hero = get_hero(user.hero_key)
        plan_label = "месяц" if plan == SubscriptionPlan.MONTHLY else "год"
        expires_str = new_expiry.strftime("%d.%m.%Y")
        logger.info("Subscription activated: user=%s plan=%s expires=%s", user.id, plan.value, expires_str)

        await state.clear()
        await callback.message.edit_reply_markup()
        await callback.message.answer(
            f"🎉 Оплата подтверждена! Подписка на *{plan_label}* активирована.\n\n"
            f"{hero.phrase('greeting')}\n\n"
            f"Действует до: *{expires_str}*",
            parse_mode="Markdown",
        )

    elif status == "pending":
        await callback.message.answer(
            "⏳ Платёж ещё обрабатывается. Подождите пару минут и нажмите *«✅ Я оплатил»* снова.",
            parse_mode="Markdown",
        )

    elif status == "canceled":
        await state.clear()
        await callback.message.edit_reply_markup()
        await callback.message.answer("❌ Платёж отменён. Попробуйте снова — /subscribe")

    else:
        await callback.message.answer(
            f"⚠️ Статус платежа: *{status}*.\nЕсли оплата прошла — напишите в поддержку.",
            parse_mode="Markdown",
        )


# ── Выбор плана → запросить email или сразу ссылку ───────────────────────────

@subscription_router.callback_query(F.data.startswith("sub:"))
async def cb_plan_selected(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    plan = callback.data.split(":")[1]  # "monthly" | "yearly"
    await callback.answer()

    user_svc = UserService(session)
    user = await user_svc.get(callback.from_user.id)

    contact = (user.phone if user and user.phone else None)
    await state.update_data(plan=plan, user_id=callback.from_user.id, contact=contact or "")

    # Step 1: get contact if missing
    if not contact:
        await state.set_state(PaymentStates.waiting_email)
        await callback.message.answer(
            "📧 Для формирования чека введите ваш *e-mail*:",
            parse_mode="Markdown",
        )
        return

    # Step 2: get city if missing
    if not (user and user.city):
        await state.set_state(PaymentStates.waiting_city)
        await callback.message.answer(
            "🏙 В каком *городе* вы живёте?\n\n_Например: Москва_",
            parse_mode="Markdown",
        )
        return

    # All data ready → create payment
    await state.update_data(city=user.city, district=user.district or "")
    await callback.message.answer("⏳ Создаём ссылку на оплату…")
    await _send_payment_link(callback.message, state)


@subscription_router.message(PaymentStates.waiting_email)
async def got_email(message: Message, state: FSMContext, session: AsyncSession) -> None:
    email = message.text.strip() if message.text else ""
    if not _EMAIL_RE.match(email):
        await message.answer("Введите корректный e-mail, например: ivan@mail.ru")
        return

    await state.update_data(contact=email)

    # Check if city already set
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if user and user.city:
        await state.update_data(city=user.city, district=user.district or "")
        await message.answer("⏳ Создаём ссылку на оплату…")
        await _send_payment_link(message, state)
        return

    await state.set_state(PaymentStates.waiting_city)
    await message.answer(
        "🏙 В каком *городе* вы живёте?\n\n_Например: Москва_",
        parse_mode="Markdown",
    )


@subscription_router.message(PaymentStates.waiting_city)
async def got_city(message: Message, state: FSMContext) -> None:
    city = message.text.strip() if message.text else ""
    if not city:
        await message.answer("Пожалуйста, введите название города.")
        return

    await state.update_data(city=city)
    await state.set_state(PaymentStates.waiting_district)
    await message.answer(
        "🏘 Введите *район* или округ:\n\n_Например: Центральный, ЗАО, Невский_",
        parse_mode="Markdown",
    )


@subscription_router.message(PaymentStates.waiting_district)
async def got_district(message: Message, state: FSMContext, session: AsyncSession) -> None:
    district = message.text.strip() if message.text else ""
    if not district:
        await message.answer("Пожалуйста, введите район.")
        return

    await state.update_data(district=district)

    # Save city/district to user profile
    data = await state.get_data()
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if user:
        await user_svc.update(user, city=data.get("city"), district=district)

    await message.answer("⏳ Создаём ссылку на оплату…")
    await _send_payment_link(message, state)
