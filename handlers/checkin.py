from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DailyLog
from habits.registry import BOOL_HABITS, HABIT_REGISTRY, SCALE_HABITS, TEXT_HABITS
from heroes.data import get_hero
from keyboards.builders import kb_scale, kb_share_report, kb_start_checkin, kb_yes_no
from services.analytics_service import AnalyticsService
from services.log_service import LogService
from services.report_service import ReportService
from services.user_service import UserService

checkin_router = Router(name="checkin")


class CheckinStates(StatesGroup):
    in_progress = State()


# ── Entry points ──────────────────────────────────────────────────────────────

@checkin_router.message(Command("checkin"))
async def cmd_checkin(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if not user or not user.onboarding_done:
        await message.answer("Сначала пройдите настройку — отправьте /start.")
        return
    await _begin_checkin(message, state, session, user.id)


@checkin_router.callback_query(F.data == "checkin:begin")
async def cb_begin_checkin(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    await _begin_checkin(callback.message, state, session, callback.from_user.id)


async def _begin_checkin(
    message: Message, state: FSMContext, session: AsyncSession, user_id: int
) -> None:
    user_svc = UserService(session)
    log_svc = LogService(session)
    user = await user_svc.get_or_raise(user_id)
    hero = get_hero(user.hero_key)

    log = await log_svc.get_today_log(user_id)
    if log and log.day_index is not None:
        await message.answer(
            f"✅ Чек-ин уже выполнен!\n\n🌟 Индекс дня: *{log.day_index} / 10*",
            parse_mode="Markdown",
        )
        return

    log = await log_svc.get_or_create_today_log(user_id)
    queue = [h for h in user.selected_habits if h in HABIT_REGISTRY]

    if not queue:
        await message.answer("Нет выбранных привычек. Пройдите настройку: /start")
        return

    await state.update_data(queue=queue, log_id=log.id, user_id=user_id)
    await state.set_state(CheckinStates.in_progress)
    await message.answer(
        f"{hero.phrase('greeting')}\n\n📋 *Отметим привычки за сегодня!*",
        parse_mode="Markdown",
    )
    await _ask_next(message, state, session)


# ── Ask next habit ────────────────────────────────────────────────────────────

async def _ask_next(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    queue: list[str] = data.get("queue", [])

    if not queue:
        await _finalize(message, state, session)
        return

    current = queue[0]
    habit = HABIT_REGISTRY[current]
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(data.get("user_id"))
    target = _get_target(user, current)
    question = habit.question(target)

    if current in SCALE_HABITS:
        await message.answer(question, reply_markup=kb_scale(f"ci_{current}"))
    elif current in BOOL_HABITS:
        await message.answer(question, reply_markup=kb_yes_no(f"ci_{current}:1", f"ci_{current}:0"))
    else:
        await message.answer(question, parse_mode="Markdown")


# ── Text handler (steps, calories, sleep) ─────────────────────────────────────

@checkin_router.message(CheckinStates.in_progress)
async def handle_text_answer(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    queue: list[str] = list(data.get("queue", []))
    if not queue:
        return
    current = queue[0]
    if current not in TEXT_HABITS:
        await message.answer("Пожалуйста, используйте кнопки ниже.")
        return
    habit = HABIT_REGISTRY[current]
    try:
        value = habit.validate(message.text.strip())
    except ValueError as e:
        await message.answer(str(e))
        return
    await _save_and_advance(message, state, session, current, value, queue)


# ── Button handler (scale / bool) ─────────────────────────────────────────────

@checkin_router.callback_query(CheckinStates.in_progress, F.data.startswith("ci_"))
async def handle_button_answer(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    queue: list[str] = list(data.get("queue", []))
    if not queue:
        await callback.answer()
        return

    current = queue[0]
    if not callback.data.startswith(f"ci_{current}"):
        await callback.answer("Дождитесь текущего вопроса.", show_alert=True)
        return

    raw = callback.data.split(":")[1]
    habit = HABIT_REGISTRY[current]
    try:
        value = habit.validate(raw)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    await callback.message.edit_reply_markup()
    await callback.answer()
    await _save_and_advance(callback.message, state, session, current, value, queue)


# ── Save & advance ────────────────────────────────────────────────────────────

_FIELD_MAP = {
    "steps": "steps", "calories": "calories", "sleep": "sleep_hours",
    "stress": "stress_level", "energy": "energy_level",
    "alcohol": "alcohol", "smoking": "smoking", "no_sugar": "no_sugar",
    "reading": "reading_amount", "meal_gap": "meal_gap",
}


async def _save_and_advance(
    message: Message, state: FSMContext, session: AsyncSession,
    habit_key: str, value, queue: list[str],
) -> None:
    data = await state.get_data()
    log_svc = LogService(session)
    log = await session.get(DailyLog, data.get("log_id"))
    await log_svc.update_log(log, **{_FIELD_MAP[habit_key]: value})

    user_svc = UserService(session)
    user = await user_svc.get_or_raise(data.get("user_id"))
    result = HABIT_REGISTRY[habit_key].evaluate(value, _get_target(user, habit_key))
    await message.answer(result.label)

    queue.pop(0)
    await state.update_data(queue=queue)
    await _ask_next(message, state, session)


# ── Finalize ──────────────────────────────────────────────────────────────────

async def _finalize(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    user_id: int = data.get("user_id")
    log_id: int = data.get("log_id")

    user_svc = UserService(session)
    log_svc = LogService(session)
    analytics = AnalyticsService()

    user = await user_svc.get_or_raise(user_id)
    hero = get_hero(user.hero_key)
    log = await session.get(DailyLog, log_id)

    day_index = analytics.calculate_day_index(log, user)
    await log_svc.update_log(log, day_index=day_index)
    log = await session.get(DailyLog, log_id)

    summary = analytics.build_day_summary(log, user)

    all_logs = await log_svc.get_all_logs(user_id)
    streaks = analytics.get_streaks(all_logs, user)
    streak_lines = [
        f"{hero.phrase('streak')} — {HABIT_REGISTRY[k].display_name} {v} {AnalyticsService._days_word(v)} подряд!"
        for k, v in streaks.items()
        if v >= 2
    ]

    text = f"{hero.phrase('done')}\n\n{summary}"
    if streak_lines:
        text += "\n\n" + "\n".join(streak_lines)

    await state.clear()
    await message.answer(text, parse_mode="Markdown")


# ── /report ───────────────────────────────────────────────────────────────────

@checkin_router.message(Command("report"))
async def cmd_report(message: Message, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if not user or not user.onboarding_done:
        await message.answer("Сначала пройдите настройку — /start.")
        return

    log_svc = LogService(session)
    analytics = AnalyticsService()
    report_svc = ReportService(analytics)

    today = date.today()
    logs = await log_svc.get_logs_between(user.id, today - timedelta(days=6), today)
    weight_logs = await log_svc.get_weight_logs(user.id)

    report = report_svc.build_weekly_report(user, logs, weight_logs)
    await message.answer(report, parse_mode="Markdown")

    # Generate and send PNG progress card
    from aiogram.types import BufferedInputFile
    from services.image_service import generate_progress_card
    try:
        img_bytes = generate_progress_card(user, logs, weight_logs, analytics)
        await message.answer_photo(
            BufferedInputFile(img_bytes, filename="progress.png"),
            caption="📸 *Карточка прогресса* — сохрани и поделись в сторис!",
            parse_mode="Markdown",
            reply_markup=kb_share_report(),
        )
    except Exception:
        # Fallback to text card if image generation fails
        card = report_svc.build_progress_card(user, logs)
        await message.answer(
            f"📋 *Карточка прогресса:*\n\n{card}",
            parse_mode="Markdown",
            reply_markup=kb_share_report(),
        )


# ── /help ─────────────────────────────────────────────────────────────────────

@checkin_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 *Справка*\n\n"
        "/checkin — ежедневный чек-ин\n"
        "/report — отчёт за 7 дней\n"
        "/weight — записать вес\n"
        "/settings — настройки\n"
        "/start — перезапуск\n"
        "/help — эта справка\n\n"
        "💳 *Подписка*\n"
        "Первые *15 дней* — бесплатно.\n"
        "После этого доступны два плана:\n"
        "• Месяц — *249 ₽*\n"
        "• Год — *1790 ₽* _(экономия 1198 ₽)_\n\n"
        "/subscribe — оформить или продлить подписку",
        parse_mode="Markdown",
    )


def _get_target(user, key: str):
    if key == "reading":
        unit = "минут" if user.reading_format == "minutes" else "страниц"
        return (user.reading_target or 30, unit)
    return {
        "steps": user.steps_target,
        "calories": user.calories_target,
        "meal_gap": user.meal_gap_target or 8,
    }.get(key)