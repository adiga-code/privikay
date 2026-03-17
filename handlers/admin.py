import io
import logging
from collections import Counter
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import DailyLog, FeedbackLog, User
from keyboards.builders import (
    kb_admin, kb_broadcast_confirm, kb_broadcast_filters, kb_broadcast_goals,
)
from services.subscription_service import SubscriptionService
from services.user_service import UserService

admin_router = Router(name="admin")
logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_id_list


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🛠 *Панель администратора*", parse_mode="Markdown", reply_markup=kb_admin())


@admin_router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    result = await session.execute(select(User))
    all_users: list[User] = list(result.scalars().all())

    now = datetime.utcnow()
    total = len(all_users)
    onboarded = sum(1 for u in all_users if u.onboarding_done)
    in_trial = sum(
        1 for u in all_users
        if u.onboarding_done and (now - u.registered_at).days < settings.trial_days
        and not (u.subscription_expires_at and u.subscription_expires_at > now)
    )
    subscribed = sum(
        1 for u in all_users
        if u.subscription_expires_at and u.subscription_expires_at > now
    )
    expired = sum(
        1 for u in all_users
        if u.onboarding_done
        and (now - u.registered_at).days >= settings.trial_days
        and not (u.subscription_expires_at and u.subscription_expires_at > now)
    )

    await callback.message.answer(
        f"📊 *Статистика пользователей*\n\n"
        f"👤 Всего зарегистрировано: *{total}*\n"
        f"✅ Прошли онбординг: *{onboarded}*\n"
        f"🕐 В бесплатном периоде: *{in_trial}*\n"
        f"💳 Активная подписка: *{subscribed}*\n"
        f"🔒 Период истёк (без подписки): *{expired}*",
        parse_mode="Markdown",
        reply_markup=kb_admin(),
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin:subs")
async def cb_subs(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    now = datetime.utcnow()
    result = await session.execute(
        select(User).where(
            User.subscription_expires_at > now
        ).order_by(User.subscription_expires_at.desc())
    )
    subs: list[User] = list(result.scalars().all())

    if not subs:
        await callback.message.answer("💳 Активных подписок нет.", reply_markup=kb_admin())
        await callback.answer()
        return

    lines = ["💳 *Активные подписки:*\n"]
    for u in subs[:20]:  # show max 20
        expires = u.subscription_expires_at.strftime("%d.%m.%Y")
        plan = "месяц" if u.subscription_plan.value == "monthly" else "год"
        lines.append(f"• {u.name} (id:{u.id}) — {plan}, до {expires}")

    if len(subs) > 20:
        lines.append(f"\n_...и ещё {len(subs) - 20}_")

    await callback.message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=kb_admin(),
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin:feedback")
async def cb_feedback(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    result = await session.execute(
        select(FeedbackLog).order_by(FeedbackLog.created_at.asc())
    )
    entries: list[FeedbackLog] = list(result.scalars().all())

    if not entries:
        await callback.message.answer("📋 Отзывов пока нет.", reply_markup=kb_admin())
        await callback.answer()
        return

    # Aggregated summary
    total = len(entries)
    useful_count = sum(1 for e in entries if e.is_useful is True)
    rec_count = sum(1 for e in entries if e.would_recommend is True)

    summary = (
        f"📋 *Отзывы бета-теста*\n\n"
        f"Всего отзывов: *{total}*\n"
        f"Считают полезным: *{useful_count}/{total}* ({useful_count * 100 // total}%)\n"
        f"Порекомендуют: *{rec_count}/{total}* ({rec_count * 100 // total}%)\n\n"
        f"📄 Подробный отчёт — в файле ниже."
    )
    await callback.message.answer(summary, parse_mode="Markdown", reply_markup=kb_admin())

    # Full export as text file
    now_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
    lines = [
        f"=== ОБРАТНАЯ СВЯЗЬ — {now_str} UTC ===",
        f"Всего отзывов: {total}",
        f"Считают полезным: {useful_count}/{total} ({useful_count * 100 // total}%)",
        f"Порекомендуют: {rec_count}/{total} ({rec_count * 100 // total}%)",
        "",
    ]
    for i, e in enumerate(entries, 1):
        useful_str = "Да" if e.is_useful else ("Нет" if e.is_useful is False else "—")
        rec_str = "Да" if e.would_recommend else ("Нет" if e.would_recommend is False else "—")
        date_str = e.created_at.strftime("%d.%m.%Y %H:%M")
        lines += [
            f"--- Отзыв #{i} (День {e.day_number}, {e.user_name}, id:{e.user_id}, {date_str}) ---",
            f"Полезен: {useful_str}",
            f"Нравится: {e.likes or '—'}",
            f"Улучшить: {e.dislikes or '—'}",
            f"Порекомендует: {rec_str}",
            "",
        ]

    file_content = "\n".join(lines).encode("utf-8")
    filename = f"feedback_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.txt"
    await bot.send_document(
        callback.from_user.id,
        BufferedInputFile(file_content, filename=filename),
        caption="📋 Полный отчёт по обратной связи",
    )
    await callback.answer()


# ── Broadcast ─────────────────────────────────────────────────────────────────

class BroadcastStates(StatesGroup):
    choosing_goal = State()   # sub-filter: which goal
    waiting_photo = State()   # optional photo
    waiting_text = State()    # message text
    confirming = State()      # confirm send


@admin_router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    await callback.message.answer(
        "📢 *Рассылка*\n\nВыбери аудиторию:",
        parse_mode="Markdown",
        reply_markup=kb_broadcast_filters(),
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("broadcast:filter:"))
async def cb_broadcast_filter(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    filt = callback.data.split(":")[2]
    if filt == "goal":
        await state.update_data(broadcast_filter=filt)
        await state.set_state(BroadcastStates.choosing_goal)
        await callback.message.answer("Выбери цель пользователей:", reply_markup=kb_broadcast_goals())
        await callback.answer()
        return

    await state.update_data(broadcast_filter=filt, broadcast_goal=None)
    await state.set_state(BroadcastStates.waiting_photo)
    await callback.message.answer(
        "📷 Прикрепи фото (или напиши «пропустить» чтобы отправить только текст):"
    )
    await callback.answer()


@admin_router.callback_query(BroadcastStates.choosing_goal, F.data.startswith("broadcast:goal:"))
async def cb_broadcast_goal(callback: CallbackQuery, state: FSMContext) -> None:
    goal = callback.data.split(":")[2]
    await state.update_data(broadcast_goal=goal)
    await state.set_state(BroadcastStates.waiting_photo)
    await callback.message.answer(
        "📷 Прикрепи фото (или напиши «пропустить» чтобы отправить только текст):"
    )
    await callback.answer()


@admin_router.message(BroadcastStates.waiting_photo)
async def got_broadcast_photo(message: Message, state: FSMContext) -> None:
    if message.photo:
        photo_id = message.photo[-1].file_id
        await state.update_data(broadcast_photo=photo_id)
    else:
        await state.update_data(broadcast_photo=None)

    await state.set_state(BroadcastStates.waiting_text)
    await message.answer("✏️ Напиши текст сообщения для рассылки:")


@admin_router.message(BroadcastStates.waiting_text)
async def got_broadcast_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("Текст не может быть пустым. Попробуй снова:")
        return

    await state.update_data(broadcast_text=text)
    data = await state.get_data()
    count = await _count_recipients(session, data)
    await state.set_state(BroadcastStates.confirming)
    await message.answer(
        f"📢 *Предпросмотр рассылки*\n\n"
        f"{text}\n\n"
        f"👥 Получателей: *{count}*\n\n"
        "Отправить?",
        parse_mode="Markdown",
        reply_markup=kb_broadcast_confirm(),
    )


@admin_router.callback_query(BroadcastStates.confirming, F.data == "broadcast:send")
async def cb_broadcast_send(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    data = await state.get_data()
    users = await _get_recipients(session, data)
    text = data.get("broadcast_text", "")
    photo_id = data.get("broadcast_photo")

    sent = 0
    failed = 0
    for user in users:
        try:
            if photo_id:
                await bot.send_photo(user.id, photo_id, caption=text, parse_mode="Markdown")
            else:
                await bot.send_message(user.id, text, parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1

    await state.clear()
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        f"✅ Рассылка завершена.\n\nОтправлено: *{sent}*\nОшибок: *{failed}*",
        parse_mode="Markdown",
        reply_markup=kb_admin(),
    )
    await callback.answer()


@admin_router.callback_query(BroadcastStates.confirming, F.data == "broadcast:cancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup()
    await callback.message.answer("❌ Рассылка отменена.", reply_markup=kb_admin())
    await callback.answer()


async def _count_recipients(session: AsyncSession, data: dict) -> int:
    return len(await _get_recipients(session, data))


async def _get_recipients(session: AsyncSession, data: dict) -> list[User]:
    filt = data.get("broadcast_filter", "all")
    goal = data.get("broadcast_goal")

    result = await session.execute(select(User).where(User.onboarding_done.is_(True)))
    users: list[User] = list(result.scalars().all())

    now = datetime.utcnow()
    sub_svc = SubscriptionService()

    if filt == "trial":
        users = [u for u in users if sub_svc.is_trial(u) and not sub_svc.is_subscribed(u)]
    elif filt == "paid":
        users = [u for u in users if sub_svc.is_subscribed(u)]
    elif filt == "goal" and goal:
        users = [u for u in users if u.goal and u.goal.value == goal]
    elif filt == "active":
        week_ago = (now - timedelta(days=7)).date()
        active_ids_result = await session.execute(
            select(DailyLog.user_id).where(DailyLog.date >= week_ago).distinct()
        )
        active_ids = set(active_ids_result.scalars().all())
        users = [u for u in users if u.id in active_ids]

    return users


@admin_router.callback_query(F.data == "admin:referrals")
async def cb_referrals(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    result = await session.execute(select(User).where(User.onboarding_done.is_(True)))
    users: list[User] = list(result.scalars().all())

    total = len(users)
    sources = Counter(u.referral_source or "органика" for u in users)

    # Summary message
    lines_msg = ["🔗 *Рефералы*\n", f"Всего пользователей (прошли онбординг): *{total}*\n"]
    for src, cnt in sources.most_common():
        pct = cnt * 100 // total if total else 0
        lines_msg.append(f"• `{src}` — *{cnt}* чел. ({pct}%)")

    await callback.message.answer(
        "\n".join(lines_msg), parse_mode="Markdown", reply_markup=kb_admin()
    )

    # Detailed file
    now_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
    file_lines = [
        f"=== РЕФЕРАЛЫ — {now_str} UTC ===",
        f"Всего: {total}",
        "",
        "--- Сводка по источникам ---",
    ]
    for src, cnt in sources.most_common():
        pct = cnt * 100 // total if total else 0
        file_lines.append(f"{src}: {cnt} ({pct}%)")

    file_lines += ["", "--- Список пользователей ---", "Имя | ID | Источник | Дата регистрации"]
    for u in sorted(users, key=lambda x: x.registered_at):
        reg = u.registered_at.strftime("%d.%m.%Y")
        src = u.referral_source or "органика"
        file_lines.append(f"{u.name} | {u.id} | {src} | {reg}")

    file_content = "\n".join(file_lines).encode("utf-8")
    filename = f"referrals_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.txt"
    await bot.send_document(
        callback.from_user.id,
        BufferedInputFile(file_content, filename=filename),
        caption="🔗 Полный список пользователей по источникам",
    )
    await callback.answer()