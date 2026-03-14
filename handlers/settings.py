from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from habits.registry import HABIT_REGISTRY
from keyboards.builders import kb_habits, kb_hero, kb_settings, kb_timezone
from services.user_service import UserService

settings_router = Router(name="settings")


class SettingsStates(StatesGroup):
    waiting_checkin_time = State()
    waiting_sleep_time = State()
    waiting_timezone = State()
    waiting_hero = State()
    waiting_habits = State()
    waiting_habit_setup = State()


@settings_router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if not user or not user.onboarding_done:
        await message.answer("Сначала пройдите настройку — /start.")
        return

    from heroes.data import get_hero
    hero = get_hero(user.hero_key)
    sign = "+" if user.timezone_offset >= 0 else ""
    local_checkin = _utc_to_local(user.checkin_time, user.timezone_offset)
    sleep_str = _utc_to_local(user.sleep_target_time, user.timezone_offset) if user.sleep_target_time else "не задано"

    await message.answer(
        f"⚙️ *Настройки*\n\n"
        f"{hero.emoji} Герой: *{hero.name}*\n"
        f"🌍 Часовой пояс: *UTC{sign}{user.timezone_offset}*\n"
        f"🕐 Чек-ин: *{local_checkin}* (местное время)\n"
        f"😴 Время сна: *{sleep_str}*\n\n"
        f"Что изменить?",
        parse_mode="Markdown",
        reply_markup=kb_settings(),
    )


# ── Setting: checkin_time ─────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings:checkin_time")
async def ask_checkin_time(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "🕐 Введите новое время чек-ина (*местное время*), например *21:00*:",
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_checkin_time)
    await callback.answer()


@settings_router.message(SettingsStates.waiting_checkin_time)
async def got_checkin_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(message.from_user.id)
    utc_str = _parse_local_time(message.text.strip(), user.timezone_offset)
    if not utc_str:
        await message.answer("Введите время в формате ЧЧ:ММ, например 21:00.")
        return
    await user_svc.update(user, checkin_time=utc_str)
    await state.clear()
    await message.answer(f"✅ Время чек-ина обновлено: *{message.text.strip()}*", parse_mode="Markdown")


# ── Setting: sleep_time ───────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings:sleep_time")
async def ask_sleep_time(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "😴 Введите время отхода ко сну (*местное время*), например *23:00*:\n\n"
        "_Введите 0 чтобы отключить напоминание._",
        parse_mode="Markdown",
    )
    await state.set_state(SettingsStates.waiting_sleep_time)
    await callback.answer()


@settings_router.message(SettingsStates.waiting_sleep_time)
async def got_sleep_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = message.text.strip()
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(message.from_user.id)

    if raw == "0":
        await user_svc.update(user, sleep_target_time=None)
        await state.clear()
        await message.answer("✅ Напоминание о сне отключено.")
        return

    utc_str = _parse_local_time(raw, user.timezone_offset)
    if not utc_str:
        await message.answer("Введите время в формате ЧЧ:ММ, например 23:00.")
        return
    await user_svc.update(user, sleep_target_time=utc_str)
    await state.clear()
    await message.answer(f"✅ Напоминание о сне обновлено: *{raw}*", parse_mode="Markdown")


# ── Setting: timezone ─────────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings:timezone")
async def ask_timezone(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup()
    await callback.message.answer("🌍 Выберите часовой пояс:", reply_markup=kb_timezone())
    await state.set_state(SettingsStates.waiting_timezone)
    await callback.answer()


@settings_router.callback_query(SettingsStates.waiting_timezone, F.data.startswith("tz:"))
async def got_timezone(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    offset = int(callback.data.split(":")[1])
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(callback.from_user.id)
    await user_svc.update(user, timezone_offset=offset)
    sign = "+" if offset >= 0 else ""
    await callback.message.edit_reply_markup()
    await state.clear()
    await callback.message.answer(
        f"✅ Часовой пояс обновлён: *UTC{sign}{offset}*\n\n"
        "_Время чек-ина и сна хранится в UTC и не изменилось. "
        "Обновите их в настройках если нужно._",
        parse_mode="Markdown",
    )
    await callback.answer()


# ── Setting: hero ─────────────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings:hero")
async def ask_hero(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup()
    await callback.message.answer("🦸 Выберите нового героя:", reply_markup=kb_hero())
    await state.set_state(SettingsStates.waiting_hero)
    await callback.answer()


@settings_router.callback_query(SettingsStates.waiting_hero, F.data.startswith("hero:"))
async def got_hero(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    hero_key = callback.data.split(":")[1]
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(callback.from_user.id)
    await user_svc.update(user, hero_key=hero_key)
    from heroes.data import get_hero
    hero = get_hero(hero_key)
    await callback.message.edit_reply_markup()
    await state.clear()
    await callback.message.answer(
        f"{hero.emoji} Герой сменён на *{hero.name}*!\n\n{hero.phrase('greeting')}",
        parse_mode="Markdown",
    )
    await callback.answer()


# ── Setting: habits ───────────────────────────────────────────────────────────

_HABIT_SETUP_PROMPTS: dict[str, str] = {
    "reading_format": (
        "📚 *Формат отслеживания чтения*\n\n"
        "*1* — в минутах\n*2* — в страницах\n\nВведите *1* или *2*:"
    ),
    "reading_target": "📚 *Цель по чтению*\n\nВведите целевое число (минуты или страницы):",
    "meal_gap_target": (
        "⏰ *Перерыв между приёмами пищи*\n\n"
        "Введите *8*, *10* или *12* (часов):"
    ),
}

_HABIT_SETUP_ERRORS: dict[str, str] = {
    "reading_format": "Введите *1* (минуты) или *2* (страницы).",
    "reading_target": "Введите целое число от 1 до 2000.",
    "meal_gap_target": "Введите *8*, *10* или *12*.",
}


@settings_router.callback_query(F.data == "settings:habits")
async def ask_habits(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.message.edit_reply_markup()
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(callback.from_user.id)
    show_weight = user.weight_goal.value != "none"
    selected: list[str] = list(user.selected_habits or [])
    await state.update_data(selected_habits=selected, show_weight=show_weight)
    await callback.message.answer(
        "✏️ *Выберите привычки*\n\nСнимите/добавьте нужные и нажмите *Продолжить*.",
        parse_mode="Markdown",
        reply_markup=kb_habits(selected=selected, show_weight=show_weight),
    )
    await state.set_state(SettingsStates.waiting_habits)
    await callback.answer()


@settings_router.callback_query(SettingsStates.waiting_habits, F.data.startswith("habit_toggle:"))
async def toggle_habit_settings(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    key = callback.data.split(":")[1]
    data = await state.get_data()
    selected: list[str] = list(data.get("selected_habits", []))
    show_weight: bool = data.get("show_weight", False)

    if key == "done":
        if not selected:
            await callback.answer("Выберите хотя бы одну привычку.", show_alert=True)
            return

        user_svc = UserService(session)
        user = await user_svc.get_or_raise(callback.from_user.id)
        await user_svc.update(user, selected_habits=selected)

        # Build setup queue for newly selected habits that need config
        queue: list[str] = []
        if "reading" in selected and user.reading_format is None:
            queue.append("reading_format")
            queue.append("reading_target")
        elif "reading" in selected and user.reading_target is None:
            queue.append("reading_target")
        if "meal_gap" in selected and user.meal_gap_target is None:
            queue.append("meal_gap_target")

        await callback.message.edit_reply_markup()
        await callback.answer()

        if queue:
            await state.update_data(habit_setup_queue=queue)
            await state.set_state(SettingsStates.waiting_habit_setup)
            await callback.message.answer(
                _HABIT_SETUP_PROMPTS[queue[0]], parse_mode="Markdown"
            )
        else:
            await state.clear()
            names = [HABIT_REGISTRY[k].display_name for k in selected if k in HABIT_REGISTRY]
            await callback.message.answer(
                f"✅ Привычки обновлены:\n{', '.join(names)}",
                parse_mode="Markdown",
            )
        return

    if key in selected:
        selected.remove(key)
    else:
        selected.append(key)
    await state.update_data(selected_habits=selected)
    await callback.message.edit_reply_markup(
        reply_markup=kb_habits(selected=selected, show_weight=show_weight)
    )
    await callback.answer()


@settings_router.message(SettingsStates.waiting_habit_setup)
async def got_habit_setup(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    queue: list[str] = list(data.get("habit_setup_queue", []))
    if not queue:
        return

    current = queue[0]
    raw = message.text.strip() if message.text else ""

    try:
        user_svc = UserService(session)
        user = await user_svc.get_or_raise(message.from_user.id)

        if current == "reading_format":
            if raw not in ("1", "2"):
                raise ValueError
            fmt = "minutes" if raw == "1" else "pages"
            await user_svc.update(user, reading_format=fmt)

        elif current == "reading_target":
            v = int(raw)
            if not (1 <= v <= 2000):
                raise ValueError
            await user_svc.update(user, reading_target=v)

        elif current == "meal_gap_target":
            v = int(raw)
            if v not in (8, 10, 12):
                raise ValueError
            await user_svc.update(user, meal_gap_target=v)

    except (ValueError, TypeError):
        await message.answer(_HABIT_SETUP_ERRORS[current], parse_mode="Markdown")
        return

    queue.pop(0)
    await state.update_data(habit_setup_queue=queue)

    if queue:
        await message.answer(_HABIT_SETUP_PROMPTS[queue[0]], parse_mode="Markdown")
    else:
        await state.clear()
        selected: list[str] = data.get("selected_habits", [])
        names = [HABIT_REGISTRY[k].display_name for k in selected if k in HABIT_REGISTRY]
        await message.answer(
            f"✅ Привычки обновлены:\n{', '.join(names)}",
            parse_mode="Markdown",
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_local_time(raw: str, tz_offset: int) -> str | None:
    """Parse local HH:MM string and return UTC HH:MM or None on error."""
    try:
        parts = raw.split(":")
        if len(parts) != 2:
            return None
        hh, mm = int(parts[0]), int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        utc_hh = (hh - tz_offset) % 24
        return f"{utc_hh:02d}:{mm:02d}"
    except (ValueError, TypeError):
        return None


def _utc_to_local(utc_str: str, tz_offset: int) -> str:
    """Convert UTC HH:MM string to local HH:MM."""
    try:
        hh, mm = map(int, utc_str.split(":"))
        local_hh = (hh + tz_offset) % 24
        return f"{local_hh:02d}:{mm:02d}"
    except Exception:
        return utc_str