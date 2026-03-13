from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.builders import kb_hero, kb_settings, kb_timezone
from services.user_service import UserService

settings_router = Router(name="settings")


class SettingsStates(StatesGroup):
    waiting_checkin_time = State()
    waiting_sleep_time = State()
    waiting_timezone = State()
    waiting_hero = State()


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