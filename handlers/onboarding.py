from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import UserGoal, WeightGoal
from keyboards.builders import (
    kb_contact, kb_goal, kb_habits, kb_hero,
    kb_remove, kb_timezone, kb_weight_goal,
)
from services.user_service import UserService

onboarding_router = Router(name="onboarding")


class OnboardingStates(StatesGroup):
    waiting_name = State()
    waiting_contact = State()
    waiting_city = State()
    waiting_district = State()
    waiting_goal = State()
    waiting_weight_goal = State()
    waiting_habits = State()
    waiting_timezone = State()   # inline keyboard
    waiting_setup = State()      # text: steps_target, calories_target, checkin_time, sleep_time
    waiting_hero = State()       # inline keyboard


# ── Entry ─────────────────────────────────────────────────────────────────────

@onboarding_router.callback_query(F.data == "onboarding:start")
async def onboarding_begin(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup()
    await callback.message.answer("Как вас зовут? Введите имя:")
    await state.set_state(OnboardingStates.waiting_name)
    await callback.answer()


# ── 1. Name ───────────────────────────────────────────────────────────────────

@onboarding_router.message(OnboardingStates.waiting_name)
async def got_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = message.text.strip()
    if not (1 <= len(name) <= 50):
        await message.answer("Введите имя от 1 до 50 символов.")
        return
    data = await state.get_data()
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if user:
        await user_svc.update(user, name=name)
    else:
        user = await user_svc.create(message.from_user.id, name)
        ref = data.get("referral_source")
        if ref:
            await user_svc.update(user, referral_source=ref)
    await state.update_data(name=name)
    await message.answer(
        f"Приятно познакомиться, *{name}*! 👋\n\nПоделитесь номером телефона или пропустите.",
        parse_mode="Markdown", reply_markup=kb_contact(),
    )
    await state.set_state(OnboardingStates.waiting_contact)


# ── 2. Contact ────────────────────────────────────────────────────────────────

@onboarding_router.message(OnboardingStates.waiting_contact, F.contact)
async def got_contact(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(message.from_user.id)
    await user_svc.update(user, phone=message.contact.phone_number)
    await _ask_city(message, state)


@onboarding_router.message(OnboardingStates.waiting_contact, F.text == "Пропустить →")
async def skip_contact(message: Message, state: FSMContext) -> None:
    await _ask_city(message, state)


@onboarding_router.message(OnboardingStates.waiting_contact)
async def contact_bad(message: Message) -> None:
    await message.answer("Нажмите кнопку «📱 Поделиться контактом» или «Пропустить →».")


# ── 2b. City & District ───────────────────────────────────────────────────────

async def _ask_city(message: Message, state: FSMContext) -> None:
    await message.answer("Хорошо!", reply_markup=kb_remove())
    await message.answer(
        "🏙 В каком *городе* вы живёте?\n\n_Например: Москва_",
        parse_mode="Markdown",
    )
    await state.set_state(OnboardingStates.waiting_city)


@onboarding_router.message(OnboardingStates.waiting_city)
async def got_city(message: Message, state: FSMContext) -> None:
    city = message.text.strip() if message.text else ""
    if not city:
        await message.answer("Пожалуйста, введите название города.")
        return
    await state.update_data(city=city)
    await message.answer(
        "🏘 Введите *район* или округ:\n\n_Например: Центральный, ЗАО, Невский_",
        parse_mode="Markdown",
    )
    await state.set_state(OnboardingStates.waiting_district)


@onboarding_router.message(OnboardingStates.waiting_district)
async def got_district(message: Message, state: FSMContext, session: AsyncSession) -> None:
    district = message.text.strip() if message.text else ""
    if not district:
        await message.answer("Пожалуйста, введите район.")
        return
    data = await state.get_data()
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(message.from_user.id)
    await user_svc.update(user, city=data.get("city"), district=district)
    await _ask_goal(message, state)


# ── 3. Goal ───────────────────────────────────────────────────────────────────

async def _ask_goal(message: Message, state: FSMContext) -> None:
    await message.answer("Выберите главную цель:", reply_markup=kb_goal())
    await state.set_state(OnboardingStates.waiting_goal)


@onboarding_router.callback_query(OnboardingStates.waiting_goal, F.data.startswith("goal:"))
async def got_goal(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(callback.from_user.id)
    await user_svc.update(user, goal=UserGoal(callback.data.split(":")[1]))
    await callback.message.edit_reply_markup()
    await callback.message.answer("Есть ли цель по весу?", reply_markup=kb_weight_goal())
    await state.set_state(OnboardingStates.waiting_weight_goal)
    await callback.answer()


# ── 4. Weight goal ────────────────────────────────────────────────────────────

@onboarding_router.callback_query(
    OnboardingStates.waiting_weight_goal, F.data.startswith("wgoal:")
)
async def got_weight_goal(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    weight_goal = WeightGoal(callback.data.split(":")[1])
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(callback.from_user.id)
    await user_svc.update(user, weight_goal=weight_goal)

    show_weight = weight_goal != WeightGoal.NONE
    await state.update_data(selected_habits=[], show_weight=show_weight)
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "Какие привычки хотите отслеживать?\nВыберите несколько и нажмите *Продолжить*.",
        parse_mode="Markdown",
        reply_markup=kb_habits(selected=[], show_weight=show_weight),
    )
    await state.set_state(OnboardingStates.waiting_habits)
    await callback.answer()


# ── 5. Habits multi-select ────────────────────────────────────────────────────

@onboarding_router.callback_query(
    OnboardingStates.waiting_habits, F.data.startswith("habit_toggle:")
)
async def toggle_habit(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
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

        # Build text setup queue (timezone handled separately)
        queue: list[str] = []
        if "steps" in selected:
            queue.append("steps_target")
        if "calories" in selected:
            queue.append("calories_target")
        if "reading" in selected:
            queue.append("reading_format")
            queue.append("reading_target")
        if "meal_gap" in selected:
            queue.append("meal_gap_target")
        queue.append("checkin_time")
        if "sleep" in selected:
            queue.append("sleep_time")

        await state.update_data(setup_queue=queue)
        await callback.message.edit_reply_markup()
        # First: timezone (inline keyboard → separate state)
        await callback.message.answer(
            "🌍 *Выберите ваш часовой пояс*\n_Нужен для точных напоминаний_",
            parse_mode="Markdown",
            reply_markup=kb_timezone(),
        )
        await state.set_state(OnboardingStates.waiting_timezone)
    else:
        if key in selected:
            selected.remove(key)
        else:
            selected.append(key)
        await state.update_data(selected_habits=selected)
        await callback.message.edit_reply_markup(
            reply_markup=kb_habits(selected=selected, show_weight=show_weight)
        )
    await callback.answer()


# ── 6. Timezone (inline) ──────────────────────────────────────────────────────

@onboarding_router.callback_query(OnboardingStates.waiting_timezone, F.data.startswith("tz:"))
async def got_timezone(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    offset = int(callback.data.split(":")[1])
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(callback.from_user.id)
    await user_svc.update(user, timezone_offset=offset)

    sign = "+" if offset >= 0 else ""
    await callback.message.edit_reply_markup()
    await callback.answer(f"UTC{sign}{offset} сохранён")

    data = await state.get_data()
    queue: list[str] = list(data.get("setup_queue", []))
    await state.set_state(OnboardingStates.waiting_setup)
    await _prompt_setup(callback.message, queue)


# ── 7. Setup queue (text inputs) ──────────────────────────────────────────────

_SETUP_PROMPTS: dict[str, str] = {
    "steps_target": (
        "👟 *Цель по шагам*\n\nПо умолчанию *15 000* шагов в день.\n"
        "Введите своё значение (от 1 000 до 50 000):"
    ),
    "calories_target": "🍎 *Цель по калориям*\n\nОт 500 до 10 000 ккал в день:",
    "reading_format": (
        "📚 *Формат отслеживания чтения*\n\n"
        "Как хотите считать?\n\n"
        "*1* — в минутах\n"
        "*2* — в страницах\n\n"
        "Введите *1* или *2*:"
    ),
    "reading_target": "📚 *Цель по чтению*\n\nВведите целевое число (минуты или страницы):",
    "meal_gap_target": (
        "⏰ *Перерыв между приёмами пищи*\n\n"
        "Выберите целевой интервал:\n\n"
        "*8* — 8 часов\n"
        "*10* — 10 часов\n"
        "*12* — 12 часов\n\n"
        "Введите *8*, *10* или *12*:"
    ),
    "checkin_time": (
        "🕐 *Время ежедневного напоминания*\n\n"
        "Введите *местное время* в формате *ЧЧ:ММ*, например *21:00*"
    ),
    "sleep_time": (
        "😴 *Время отхода ко сну*\n\n"
        "Я пришлю мягкое напоминание за 30 минут.\n"
        "Введите *местное время*, например *23:00*"
    ),
}

_SETUP_ERRORS: dict[str, str] = {
    "steps_target": "Введите целое число от 1 000 до 50 000.",
    "calories_target": "Введите целое число от 500 до 10 000.",
    "reading_format": "Введите *1* (минуты) или *2* (страницы).",
    "reading_target": "Введите целое число от 1 до 2000.",
    "meal_gap_target": "Введите *8*, *10* или *12*.",
    "checkin_time": "Введите время в формате ЧЧ:ММ, например 21:00.",
    "sleep_time": "Введите время в формате ЧЧ:ММ, например 23:00.",
}


async def _prompt_setup(message: Message, queue: list[str]) -> None:
    if queue:
        await message.answer(_SETUP_PROMPTS[queue[0]], parse_mode="Markdown")


@onboarding_router.message(OnboardingStates.waiting_setup)
async def got_setup_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    queue: list[str] = list(data.get("setup_queue", []))
    if not queue:
        return

    current = queue[0]
    raw = message.text.strip()

    try:
        user_svc = UserService(session)
        user = await user_svc.get_or_raise(message.from_user.id)

        if current == "steps_target":
            v = int(raw)
            if not (1_000 <= v <= 50_000):
                raise ValueError
            await user_svc.update(user, steps_target=v)

        elif current == "calories_target":
            v = int(raw)
            if not (500 <= v <= 10_000):
                raise ValueError
            await user_svc.update(user, calories_target=v)

        elif current == "reading_format":
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

        elif current in ("checkin_time", "sleep_time"):
            parts = raw.split(":")
            if len(parts) != 2:
                raise ValueError
            hh, mm = int(parts[0]), int(parts[1])
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
            # Convert local → UTC
            utc_hh = (hh - user.timezone_offset) % 24
            utc_str = f"{utc_hh:02d}:{mm:02d}"
            if current == "checkin_time":
                await user_svc.update(user, checkin_time=utc_str)
            else:
                await user_svc.update(user, sleep_target_time=utc_str)

    except (ValueError, TypeError):
        await message.answer(_SETUP_ERRORS[current])
        return

    queue.pop(0)
    await state.update_data(setup_queue=queue)

    if queue:
        await _prompt_setup(message, queue)
    else:
        await _ask_hero(message, state)


# ── 8. Hero selection (inline) ────────────────────────────────────────────────

async def _ask_hero(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.waiting_hero)
    await message.answer(
        "🦸 *Выберите своего героя!*\n\n"
        "Он будет сопровождать вас в боте и делать его более живым.",
        parse_mode="Markdown",
        reply_markup=kb_hero(),
    )


@onboarding_router.callback_query(OnboardingStates.waiting_hero, F.data.startswith("hero:"))
async def got_hero(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    hero_key = callback.data.split(":")[1]
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(callback.from_user.id)
    await user_svc.update(user, hero_key=hero_key, onboarding_done=True)

    from heroes.data import get_hero
    hero = get_hero(hero_key)
    data = await state.get_data()
    name = data.get("name", user.name)
    await state.clear()

    await callback.message.edit_reply_markup()
    await callback.message.answer(
        f"{hero.emoji} *Отлично, {name}!*\n\n"
        f"Твой герой — *{hero.name}*. Он будет с тобой каждый день.\n\n"
        "Доступные команды:\n"
        "/checkin — отметить привычки прямо сейчас\n"
        "/report — недельный отчёт\n"
        "/subscribe — подписка\n"
        "/settings — настройки\n"
        "/help — справка",
        parse_mode="Markdown",
    )
    await callback.answer()