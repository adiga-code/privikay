import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import FeedbackLog
from keyboards.builders import kb_feedback_recommend, kb_feedback_skip, kb_feedback_useful

feedback_router = Router(name="feedback")
logger = logging.getLogger(__name__)


class FeedbackStates(StatesGroup):
    likes = State()
    dislikes = State()
    would_recommend = State()


# ── Step 1: useful? (callback from scheduler message) ─────────────────────────

@feedback_router.callback_query(F.data.regexp(r"^feedback:(yes|no):\d+$"))
async def cb_useful(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    is_useful = parts[1] == "yes"
    day_number = int(parts[2])

    await state.set_data({"is_useful": is_useful, "day_number": day_number})
    await state.set_state(FeedbackStates.likes)

    emoji = "🎉" if is_useful else "😔"
    await callback.message.edit_text(
        f"{emoji} Понял!\n\n"
        f"*Что тебе нравится* больше всего в боте?\n\n"
        f"_Напиши пару слов или нажми «Пропустить»_",
        parse_mode="Markdown",
        reply_markup=kb_feedback_skip("feedback:skip_likes"),
    )
    await callback.answer()


# ── Step 2a: skip likes ────────────────────────────────────────────────────────

@feedback_router.callback_query(F.data == "feedback:skip_likes", FeedbackStates.likes)
async def cb_skip_likes(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(likes=None)
    await state.set_state(FeedbackStates.dislikes)
    await callback.message.edit_text(
        "🔧 *Что хотел бы улучшить* или чего не хватает?\n\n"
        "_Напиши или нажми «Пропустить»_",
        parse_mode="Markdown",
        reply_markup=kb_feedback_skip("feedback:skip_dislikes"),
    )
    await callback.answer()


# ── Step 2b: type likes ────────────────────────────────────────────────────────

@feedback_router.message(FeedbackStates.likes)
async def msg_likes(message: Message, state: FSMContext) -> None:
    await state.update_data(likes=message.text[:2000] if message.text else None)
    await state.set_state(FeedbackStates.dislikes)
    await message.answer(
        "🔧 *Что хотел бы улучшить* или чего не хватает?\n\n"
        "_Напиши или нажми «Пропустить»_",
        parse_mode="Markdown",
        reply_markup=kb_feedback_skip("feedback:skip_dislikes"),
    )


# ── Step 3a: skip dislikes ─────────────────────────────────────────────────────

@feedback_router.callback_query(F.data == "feedback:skip_dislikes", FeedbackStates.dislikes)
async def cb_skip_dislikes(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(dislikes=None)
    await state.set_state(FeedbackStates.would_recommend)
    await callback.message.edit_text(
        "📣 *Порекомендовал бы бот друзьям?*",
        parse_mode="Markdown",
        reply_markup=kb_feedback_recommend(),
    )
    await callback.answer()


# ── Step 3b: type dislikes ─────────────────────────────────────────────────────

@feedback_router.message(FeedbackStates.dislikes)
async def msg_dislikes(message: Message, state: FSMContext) -> None:
    await state.update_data(dislikes=message.text[:2000] if message.text else None)
    await state.set_state(FeedbackStates.would_recommend)
    await message.answer(
        "📣 *Порекомендовал бы бот друзьям?*",
        parse_mode="Markdown",
        reply_markup=kb_feedback_recommend(),
    )


# ── Step 4: would recommend? → save ───────────────────────────────────────────

@feedback_router.callback_query(
    F.data.regexp(r"^feedback:recommend:(yes|no)$"),
    FeedbackStates.would_recommend,
)
async def cb_recommend(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    would_recommend = callback.data.endswith(":yes")
    fsm_data = await state.get_data()
    await state.clear()

    entry = FeedbackLog(
        user_id=callback.from_user.id,
        user_name=callback.from_user.full_name or "",
        day_number=fsm_data.get("day_number", 0),
        is_useful=fsm_data.get("is_useful"),
        likes=fsm_data.get("likes"),
        dislikes=fsm_data.get("dislikes"),
        would_recommend=would_recommend,
    )
    session.add(entry)
    await session.commit()

    await callback.message.edit_text(
        "🙏 *Спасибо за отзыв!*\n\n"
        "Твоё мнение помогает нам становиться лучше.",
        parse_mode="Markdown",
    )
    await callback.answer()

    # Notify admins
    rec_text = "порекомендует ✅" if would_recommend else "пока нет 🤔"
    useful_text = "Да ✅" if fsm_data.get("is_useful") else "Нет ❌"
    admin_msg = (
        f"📋 *Новый отзыв* (день {fsm_data.get('day_number', '?')})\n"
        f"👤 {callback.from_user.full_name} (id:{callback.from_user.id})\n"
        f"Полезен: {useful_text}\n"
        f"Нравится: {fsm_data.get('likes') or '—'}\n"
        f"Улучшить: {fsm_data.get('dislikes') or '—'}\n"
        f"Рекомендует: {rec_text}"
    )
    for admin_id in settings.admin_id_list:
        try:
            await bot.send_message(admin_id, admin_msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Admin notify failed id=%s: %s", admin_id, e)
