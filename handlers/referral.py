from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.builders import kb_invite_friends, kb_support_friends
from services.user_service import UserService

referral_router = Router(name="referral")


@referral_router.message(Command("referral"))
async def cmd_referral(message: Message, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if not user or not user.onboarding_done:
        await message.answer("Сначала пройдите настройку — /start.")
        return
    await _show_referral(message, user, message.bot)


async def _show_referral(message: Message, user, bot) -> None:
    bot_info = await bot.get_me()
    count = user.referral_count or 0
    reward_text = "✅ Бонус уже получен!" if user.referral_reward_given else f"Пригласи *3 друзей* и получи *21 день подписки бесплатно*.\nПриглашено: *{count}/3*"

    await message.answer(
        f"🔗 *Твоя реферальная ссылка:*\n\n"
        f"`https://t.me/{bot_info.username}?start=ref_{user.id}`\n\n"
        f"{reward_text}\n\n"
        "Засчитываются только *новые* пользователи, которые ещё не запускали бота.",
        parse_mode="Markdown",
        reply_markup=kb_invite_friends(bot_info.username, user.id),
    )


@referral_router.callback_query(F.data.startswith("referral:copy:"))
async def cb_copy_link(callback: CallbackQuery) -> None:
    user_id = callback.data.split(":")[2]
    bot_info = await callback.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    await callback.answer(link, show_alert=True)


# ── "Начать с друзьями" offer (shown after 3-day streak / referral reward) ────

@referral_router.callback_query(F.data == "group:later")
async def cb_group_later(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup()
    await callback.answer("Хорошо! Можешь вернуться в любой момент через /groups")


@referral_router.callback_query(F.data == "group:start")
async def cb_group_start(callback: CallbackQuery) -> None:
    from keyboards.builders import kb_group_choice
    await callback.message.edit_reply_markup()
    await callback.answer()
    await callback.message.answer(
        "👥 *Группы поддержки*\n\n"
        "Ты можешь создать группу или присоединиться к группе друзей.",
        parse_mode="Markdown",
        reply_markup=kb_group_choice(),
    )
