import random
import string
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import GroupMember, SupportGroup, User
from keyboards.builders import kb_group_choice, kb_group_share
from services.user_service import UserService

groups_router = Router(name="groups")

_MAX_GROUP_SIZE = 5
_MIN_GROUP_SIZE = 2


class GroupStates(StatesGroup):
    waiting_code = State()


# ── Entry ─────────────────────────────────────────────────────────────────────

@groups_router.message(Command("groups"))
async def cmd_groups(message: Message, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get(message.from_user.id)
    if not user or not user.onboarding_done:
        await message.answer("Сначала пройдите настройку — /start.")
        return

    if user.group_id:
        await _show_group_info(message, session, user)
    else:
        await message.answer(
            "👥 *Группы поддержки*\n\n"
            "Ты можешь создать группу или присоединиться к группе друзей.\n\n"
            "Минимум 2 участника, максимум 5.",
            parse_mode="Markdown",
            reply_markup=kb_group_choice(),
        )


@groups_router.callback_query(F.data == "group:create")
async def cb_create_group(callback: CallbackQuery, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(callback.from_user.id)

    if user.group_id:
        await callback.answer("Ты уже состоишь в группе.", show_alert=True)
        return

    code = _generate_code()
    group = SupportGroup(code=code, creator_id=user.id)
    session.add(group)
    await session.flush()  # get group.id

    member = GroupMember(group_id=group.id, user_id=user.id)
    session.add(member)
    await user_svc.update(user, group_id=group.id)
    await session.commit()

    await callback.message.edit_reply_markup()
    await callback.answer()
    await callback.message.answer(
        f"✅ *Группа поддержки создана!*\n\n"
        f"Код группы: `{code}`\n\n"
        "Отправь этот код друзьям, чтобы они присоединились.",
        parse_mode="Markdown",
        reply_markup=kb_group_share(code),
    )


@groups_router.callback_query(F.data == "group:join")
async def cb_join_group(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup()
    await callback.answer()
    await state.set_state(GroupStates.waiting_code)
    await callback.message.answer(
        "🔑 Введи код группы:\n_Например: MOVE742_",
        parse_mode="Markdown",
    )


@groups_router.message(GroupStates.waiting_code)
async def got_group_code(message: Message, state: FSMContext, session: AsyncSession) -> None:
    code = message.text.strip().upper() if message.text else ""
    user_svc = UserService(session)
    user = await user_svc.get_or_raise(message.from_user.id)

    if user.group_id:
        await state.clear()
        await message.answer("Ты уже состоишь в группе. Сначала выйди из текущей.")
        return

    result = await session.execute(select(SupportGroup).where(SupportGroup.code == code))
    group = result.scalar_one_or_none()
    if not group:
        await message.answer("❌ Группа с таким кодом не найдена. Проверь код и попробуй снова.")
        return

    # Check size
    members_result = await session.execute(
        select(GroupMember).where(GroupMember.group_id == group.id)
    )
    members = members_result.scalars().all()
    if len(members) >= _MAX_GROUP_SIZE:
        await message.answer(f"❌ Группа уже заполнена (максимум {_MAX_GROUP_SIZE} участников).")
        return

    member = GroupMember(group_id=group.id, user_id=user.id)
    session.add(member)
    await user_svc.update(user, group_id=group.id)
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ Ты присоединился к группе *{code}*!\n\n"
        "Теперь вы будете проходить привычки вместе.",
        parse_mode="Markdown",
    )

    # Notify other members
    other_ids = [m.user_id for m in members if m.user_id != user.id]
    for uid in other_ids:
        try:
            await message.bot.send_message(
                uid,
                f"👋 К вашей группе поддержки присоединился новый участник — *{user.name}*!",
                parse_mode="Markdown",
            )
        except Exception:
            pass


@groups_router.callback_query(F.data.startswith("group:copy:"))
async def cb_copy_code(callback: CallbackQuery) -> None:
    code = callback.data.split(":")[2]
    await callback.answer(f"Код группы: {code}", show_alert=True)


# ── Group info ─────────────────────────────────────────────────────────────────

async def _show_group_info(message: Message, session: AsyncSession, user: User) -> None:
    result = await session.execute(select(SupportGroup).where(SupportGroup.id == user.group_id))
    group = result.scalar_one_or_none()
    if not group:
        await message.answer("Группа не найдена.")
        return

    members_result = await session.execute(
        select(GroupMember).where(GroupMember.group_id == group.id)
    )
    member_ids = [m.user_id for m in members_result.scalars().all()]

    names = []
    for uid in member_ids:
        u_result = await session.execute(select(User).where(User.id == uid))
        u = u_result.scalar_one_or_none()
        if u:
            names.append(u.name)

    await message.answer(
        f"👥 *Твоя группа поддержки*\n\n"
        f"Код: `{group.code}`\n"
        f"Участники: {', '.join(names)}\n"
        f"Серия группы: *{group.streak} дн.*\n\n"
        "Отправь код друзьям, чтобы они присоединились.",
        parse_mode="Markdown",
        reply_markup=kb_group_share(group.code),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_code() -> str:
    letters = "".join(random.choices(string.ascii_uppercase, k=4))
    digits = "".join(random.choices(string.digits, k=3))
    return letters + digits
