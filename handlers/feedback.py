import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import FeedbackLog
from keyboards.builders import kb_feedback_entry, kb_feedback_recommend, kb_feedback_skip, kb_feedback_useful

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


# ══════════════════════════════════════════════════════════════════════════════
# Open (free-text) feedback — /feedback command + auto-send
# ══════════════════════════════════════════════════════════════════════════════

_FEEDBACK_INTRO = (
    "И ещё один маленький вопрос 🙏\n\n"
    "*Нам очень важна твоя обратная связь на этом этапе.*\n\n"
    "Напиши, пожалуйста:\n"
    "— что тебе нравится в боте\n"
    "— что не нравится\n"
    "— что хотелось бы добавить или изменить\n\n"
    "Можно коротко или подробно — как удобно.\n"
    "Мы всё читаем и готовы улучшать продукт вместе с вами."
)


class OpenFeedbackStates(StatesGroup):
    likes = State()
    dislikes = State()
    suggestions = State()


# ── Entry: /feedback command ───────────────────────────────────────────────────

@feedback_router.message(Command("feedback"))
async def cmd_feedback(message: Message) -> None:
    await message.answer(_FEEDBACK_INTRO, parse_mode="Markdown", reply_markup=kb_feedback_entry())


# ── Entry: "Изменить настройки" button ────────────────────────────────────────

@feedback_router.callback_query(F.data == "settings:open")
async def cb_open_settings(callback: CallbackQuery) -> None:
    from keyboards.builders import kb_settings
    await callback.message.edit_reply_markup()
    await callback.message.answer("⚙️ *Настройки*", parse_mode="Markdown", reply_markup=kb_settings())
    await callback.answer()


# ── Entry: "Оставить отзыв" button ────────────────────────────────────────────

@feedback_router.callback_query(F.data == "open_feedback:start")
async def cb_open_feedback_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup()
    await callback.answer()
    await state.set_state(OpenFeedbackStates.likes)
    await callback.message.answer(
        "💚 *Что тебе нравится в боте?*\n\n_Напиши свободно — любые мысли._",
        parse_mode="Markdown",
    )


# ── Step 1: likes ──────────────────────────────────────────────────────────────

@feedback_router.message(OpenFeedbackStates.likes)
async def of_likes(message: Message, state: FSMContext) -> None:
    await state.update_data(likes=message.text[:2000] if message.text else None)
    await state.set_state(OpenFeedbackStates.dislikes)
    await message.answer(
        "👎 *Что не нравится или раздражает?*\n\n_Что стоит исправить в первую очередь?_",
        parse_mode="Markdown",
    )


# ── Step 2: dislikes ───────────────────────────────────────────────────────────

@feedback_router.message(OpenFeedbackStates.dislikes)
async def of_dislikes(message: Message, state: FSMContext) -> None:
    await state.update_data(dislikes=message.text[:2000] if message.text else None)
    await state.set_state(OpenFeedbackStates.suggestions)
    await message.answer(
        "💡 *Что хотелось бы добавить или изменить?*\n\n_Любые идеи — ценны._",
        parse_mode="Markdown",
    )


# ── Step 3: suggestions → save ────────────────────────────────────────────────

@feedback_router.message(OpenFeedbackStates.suggestions)
async def of_suggestions(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    fsm_data = await state.get_data()
    await state.clear()

    suggestions = message.text[:2000] if message.text else None

    entry = FeedbackLog(
        user_id=message.from_user.id,
        user_name=message.from_user.full_name or "",
        day_number=0,  # 0 = voluntary, not scheduled
        likes=fsm_data.get("likes"),
        dislikes=fsm_data.get("dislikes"),
        suggestions=suggestions,
    )
    session.add(entry)
    await session.commit()

    await message.answer(
        "🙏 *Спасибо! Данные обновлены.*\n\n"
        "Твой отзыв уже у нас — читаем и улучшаем бот.",
        parse_mode="Markdown",
    )

    admin_msg = (
        f"💬 *Свободный отзыв*\n"
        f"👤 {message.from_user.full_name} (id:{message.from_user.id})\n\n"
        f"💚 Нравится: {fsm_data.get('likes') or '—'}\n\n"
        f"👎 Не нравится: {fsm_data.get('dislikes') or '—'}\n\n"
        f"💡 Идеи: {suggestions or '—'}"
    )
    for admin_id in settings.admin_id_list:
        try:
            await bot.send_message(admin_id, admin_msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Admin notify failed id=%s: %s", admin_id, e)
