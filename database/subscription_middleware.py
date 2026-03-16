from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from config import settings
from services.subscription_service import SubscriptionService

# Commands and callback prefixes that bypass the paywall
_ALLOWED_COMMANDS = frozenset({"/start", "/help", "/subscribe", "/admin", "/feedback"})
_ALLOWED_CB_PREFIXES = (
    "onboarding:", "goal:", "wgoal:", "habit_toggle:",
    "tz:", "hero:", "sub:", "checkin:begin",
    "feedback:",       # structured feedback survey
    "open_feedback:",  # free-text feedback
    "settings:open",   # settings from feedback message
)


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = event

        # --- Determine user_id and whether to bypass ---
        user_id: int | None = None

        if update.message:
            msg = update.message
            # Always pass through: payments, contacts (onboarding)
            if msg.successful_payment or msg.contact:
                return await handler(event, data)
            # Allowed commands
            if msg.text and msg.text.startswith("/"):
                cmd = msg.text.split()[0].lower().split("@")[0]
                if cmd in _ALLOWED_COMMANDS:
                    return await handler(event, data)
            # Allow email input during subscription flow (waiting_email FSM state)
            # and text input during feedback survey
            fsm_state = data.get("state")
            if fsm_state is not None:
                current = await fsm_state.get_state()
                if current in (
                    "PaymentStates:waiting_email",
                    "FeedbackStates:likes",
                    "FeedbackStates:dislikes",
                    "OpenFeedbackStates:likes",
                    "OpenFeedbackStates:dislikes",
                    "OpenFeedbackStates:suggestions",
                ):
                    return await handler(event, data)
            user_id = msg.from_user.id if msg.from_user else None

        elif update.callback_query:
            cb_data = update.callback_query.data or ""
            if any(cb_data.startswith(p) for p in _ALLOWED_CB_PREFIXES):
                return await handler(event, data)
            user_id = update.callback_query.from_user.id

        elif update.pre_checkout_query:
            return await handler(event, data)

        if user_id is None:
            return await handler(event, data)

        # Admins always pass
        if user_id in settings.admin_id_list:
            return await handler(event, data)

        # --- Check subscription ---
        session = data.get("session")
        if session is None:
            return await handler(event, data)

        from services.user_service import UserService
        user_svc = UserService(session)
        user = await user_svc.get(user_id)

        # No user or still in onboarding → pass (let handlers deal with it)
        if user is None or not user.onboarding_done:
            return await handler(event, data)

        sub_svc = SubscriptionService()
        if sub_svc.is_active(user):
            return await handler(event, data)

        # --- Paywall ---
        from heroes.data import get_hero
        from keyboards.builders import kb_subscribe

        hero = get_hero(user.hero_key)
        days_trial = sub_svc.trial_days_left(user)

        if update.message:
            await update.message.answer(
                f"{hero.phrase('paywall')}\n\n"
                f"🔒 Бесплатный период закончился.\n"
                f"Оформите подписку, чтобы продолжить отслеживать привычки.",
                reply_markup=kb_subscribe(),
            )
        elif update.callback_query:
            await update.callback_query.answer(
                "Бесплатный период закончился. Нужна подписка.", show_alert=True
            )
            await update.callback_query.message.answer(
                f"{hero.phrase('paywall')}\n\n"
                f"🔒 Оформите подписку, чтобы продолжить.",
                reply_markup=kb_subscribe(),
            )

        return  # block handler