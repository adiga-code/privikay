from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WeightGoal
from keyboards.builders import kb_start_weight
from services.log_service import LogService
from services.user_service import UserService

weight_router = Router(name="weight")


class WeightStates(StatesGroup):
    waiting_weight = State()


@weight_router.callback_query(F.data == "weight:begin")
async def cb_weight_begin(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer(
        "⚖️ Введите ваш текущий вес в кг (например: *72.5*):",
        parse_mode="Markdown",
    )
    await state.set_state(WeightStates.waiting_weight)


@weight_router.message(Command("weight"))
async def cmd_weight(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if not user or not user.onboarding_done:
        await message.answer("Сначала пройдите настройку — /start.")
        return
    if user.weight_goal == WeightGoal.NONE:
        await message.answer("Вы не выбрали цель по весу.")
        return
    await message.answer("⚖️ Введите ваш текущий вес в кг (например: *72.5*):", parse_mode="Markdown")
    await state.set_state(WeightStates.waiting_weight)


@weight_router.message(WeightStates.waiting_weight)
async def got_weight(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = message.text.strip().replace(",", ".")
    try:
        weight = float(raw)
        if not (20.0 <= weight <= 300.0):
            raise ValueError
    except ValueError:
        await message.answer("Введите вес в кг (например: 72.5).")
        return

    log_svc = LogService(session)
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(message.from_user.id)
    await log_svc.add_weight(user.id, weight)
    await user_svc.update(user, last_weight_check=date.today())

    all_weights = await log_svc.get_weight_logs(user.id)
    lines = [f"✅ Вес *{weight} кг* записан."]

    if len(all_weights) >= 2:
        diff = weight - all_weights[-2].weight
        sign = "+" if diff > 0 else ""
        lines.append(f"За прошлую неделю: *{sign}{diff:.1f} кг*")

    if len(all_weights) >= 2:
        total = weight - all_weights[0].weight
        sign = "+" if total > 0 else ""
        lines.append(f"С начала: *{sign}{total:.1f} кг*")

    if len(all_weights) == 1:
        lines.append(
            "\n_Взвешиваемся раз в неделю — ежедневный вес колеблется "
            "из-за воды и питания, недельная динамика точнее._"
        )

    await state.clear()
    await message.answer("\n".join(lines), parse_mode="Markdown")