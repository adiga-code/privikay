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

    # Parse referral parameter
    ref = (command.args or "").strip()[:100] or None

    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)

    # Distinguish user referral (ref_12345) vs blogger referral (ref_blogger_name)
    referrer_id: int | None = None
    if ref and ref.startswith("ref_"):
        suffix = ref[4:]
        if suffix.isdigit():
            rid = int(suffix)
            # Only credit if it's a different user and this user is new
            if rid != message.from_user.id:
                referrer_id = rid
        else:
            # Blogger/marketing ref — save as referral_source
            if user and user.referral_source is None:
                await user_svc.update(user, referral_source=ref)

    # If new user came via user referral, save referrer_id and increment referrer's count
    if referrer_id and (user is None or user.referrer_id is None):
        if user:
            await user_svc.update(user, referrer_id=referrer_id)
        # Increment referrer's count and check for bonus
        referrer = await user_svc.get(referrer_id)
        if referrer:
            new_count = (referrer.referral_count or 0) + 1
            await user_svc.update(referrer, referral_count=new_count)
            if new_count >= 3 and not referrer.referral_reward_given:
                from datetime import timedelta
                new_exp = max(
                    referrer.subscription_expires_at or __import__('datetime').datetime.utcnow(),
                    __import__('datetime').datetime.utcnow(),
                ) + timedelta(days=21)
                await user_svc.update(referrer, subscription_expires_at=new_exp, referral_reward_given=True)
                try:
                    await message.bot.send_message(
                        referrer_id,
                        "🎉 Ты пригласил 3 новых пользователей!\n\n"
                        "Тебе начислен бонус — *21 день подписки бесплатно*.\n"
                        "Спасибо, что приглашаешь друзей! 🙏",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

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

    # Store refs in FSM so onboarding can save them when creating the user
    if ref:
        await state.update_data(referral_source=ref if not (ref.startswith("ref_") and ref[4:].isdigit()) else None)
    if referrer_id:
        await state.update_data(referrer_id=referrer_id)

    await message.answer(WELCOME_TEXT, parse_mode="Markdown", reply_markup=kb_start())