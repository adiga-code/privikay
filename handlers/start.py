from aiogram import Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.builders import kb_start
from services.subscription_service import SubscriptionService
from services.user_service import UserService

start_router = Router(name="start")

WELCOME_TEXT = (
    "👋 Привет!\n\n"
    "Я *Habit Tracker* — бот для формирования ежедневных привычек.\n\n"
    "🕐 Каждый день это займёт менее *одной минуты*.\n"
    "Я помогу:\n"
    "— улучшить режим и самочувствие\n"
    "— отслеживать прогресс\n"
    "— замечать результаты\n\n"
    "Первые *15 дней* — бесплатно.\n\n"
    "Готов начать?"
)


@start_router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()

    # Parse referral parameter: /start ref_blogger1
    ref = (command.args or "").strip()[:100] or None

    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)

    # Save referral source on first visit (don't overwrite existing)
    if ref and user and user.referral_source is None:
        await user_svc.update(user, referral_source=ref)

    if user and user.onboarding_done:
        sub_svc = SubscriptionService()
        from heroes.data import get_hero
        hero = get_hero(user.hero_key)

        if sub_svc.is_trial(user):
            days = sub_svc.trial_days_left(user)
            extra = f"🕐 Бесплатный период: ещё *{days} дн.*\n\n"
        elif sub_svc.is_subscribed(user):
            days = sub_svc.subscription_days_left(user)
            extra = f"💳 Подписка активна: ещё *{days} дн.*\n\n"
        else:
            from keyboards.builders import kb_subscribe
            await message.answer(
                f"{hero.phrase('paywall')}\n\n🔒 Бесплатный период закончился.",
                reply_markup=kb_subscribe(),
            )
            return

        await message.answer(
            f"{hero.emoji} С возвращением, *{user.name}*!\n\n"
            f"{extra}"
            "/checkin — отметить привычки\n"
            "/report — недельный отчёт\n"
            "/subscribe — подписка\n"
            "/settings — настройки\n"
            "/help — справка",
            parse_mode="Markdown",
        )
        return

    # Store ref in FSM so onboarding can save it when creating the user
    if ref:
        await state.update_data(referral_source=ref)

    await message.answer(WELCOME_TEXT, parse_mode="Markdown", reply_markup=kb_start())