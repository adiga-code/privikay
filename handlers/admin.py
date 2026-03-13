import io
import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import FeedbackLog, User
from keyboards.builders import kb_admin
from services.user_service import UserService

admin_router = Router(name="admin")
logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_id_list


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🛠 *Панель администратора*", parse_mode="Markdown", reply_markup=kb_admin())


@admin_router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    result = await session.execute(select(User))
    all_users: list[User] = list(result.scalars().all())

    now = datetime.utcnow()
    total = len(all_users)
    onboarded = sum(1 for u in all_users if u.onboarding_done)
    in_trial = sum(
        1 for u in all_users
        if u.onboarding_done and (now - u.registered_at).days < settings.trial_days
        and not (u.subscription_expires_at and u.subscription_expires_at > now)
    )
    subscribed = sum(
        1 for u in all_users
        if u.subscription_expires_at and u.subscription_expires_at > now
    )
    expired = sum(
        1 for u in all_users
        if u.onboarding_done
        and (now - u.registered_at).days >= settings.trial_days
        and not (u.subscription_expires_at and u.subscription_expires_at > now)
    )

    await callback.message.answer(
        f"📊 *Статистика пользователей*\n\n"
        f"👤 Всего зарегистрировано: *{total}*\n"
        f"✅ Прошли онбординг: *{onboarded}*\n"
        f"🕐 В бесплатном периоде: *{in_trial}*\n"
        f"💳 Активная подписка: *{subscribed}*\n"
        f"🔒 Период истёк (без подписки): *{expired}*",
        parse_mode="Markdown",
        reply_markup=kb_admin(),
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin:subs")
async def cb_subs(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    now = datetime.utcnow()
    result = await session.execute(
        select(User).where(
            User.subscription_expires_at > now
        ).order_by(User.subscription_expires_at.desc())
    )
    subs: list[User] = list(result.scalars().all())

    if not subs:
        await callback.message.answer("💳 Активных подписок нет.", reply_markup=kb_admin())
        await callback.answer()
        return

    lines = ["💳 *Активные подписки:*\n"]
    for u in subs[:20]:  # show max 20
        expires = u.subscription_expires_at.strftime("%d.%m.%Y")
        plan = "месяц" if u.subscription_plan.value == "monthly" else "год"
        lines.append(f"• {u.name} (id:{u.id}) — {plan}, до {expires}")

    if len(subs) > 20:
        lines.append(f"\n_...и ещё {len(subs) - 20}_")

    await callback.message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=kb_admin(),
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin:feedback")
async def cb_feedback(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    result = await session.execute(
        select(FeedbackLog).order_by(FeedbackLog.created_at.asc())
    )
    entries: list[FeedbackLog] = list(result.scalars().all())

    if not entries:
        await callback.message.answer("📋 Отзывов пока нет.", reply_markup=kb_admin())
        await callback.answer()
        return

    # Aggregated summary
    total = len(entries)
    useful_count = sum(1 for e in entries if e.is_useful is True)
    rec_count = sum(1 for e in entries if e.would_recommend is True)

    summary = (
        f"📋 *Отзывы бета-теста*\n\n"
        f"Всего отзывов: *{total}*\n"
        f"Считают полезным: *{useful_count}/{total}* ({useful_count * 100 // total}%)\n"
        f"Порекомендуют: *{rec_count}/{total}* ({rec_count * 100 // total}%)\n\n"
        f"📄 Подробный отчёт — в файле ниже."
    )
    await callback.message.answer(summary, parse_mode="Markdown", reply_markup=kb_admin())

    # Full export as text file
    now_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
    lines = [
        f"=== ОБРАТНАЯ СВЯЗЬ — {now_str} UTC ===",
        f"Всего отзывов: {total}",
        f"Считают полезным: {useful_count}/{total} ({useful_count * 100 // total}%)",
        f"Порекомендуют: {rec_count}/{total} ({rec_count * 100 // total}%)",
        "",
    ]
    for i, e in enumerate(entries, 1):
        useful_str = "Да" if e.is_useful else ("Нет" if e.is_useful is False else "—")
        rec_str = "Да" if e.would_recommend else ("Нет" if e.would_recommend is False else "—")
        date_str = e.created_at.strftime("%d.%m.%Y %H:%M")
        lines += [
            f"--- Отзыв #{i} (День {e.day_number}, {e.user_name}, id:{e.user_id}, {date_str}) ---",
            f"Полезен: {useful_str}",
            f"Нравится: {e.likes or '—'}",
            f"Улучшить: {e.dislikes or '—'}",
            f"Порекомендует: {rec_str}",
            "",
        ]

    file_content = "\n".join(lines).encode("utf-8")
    filename = f"feedback_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.txt"
    await bot.send_document(
        callback.from_user.id,
        BufferedInputFile(file_content, filename=filename),
        caption="📋 Полный отчёт по обратной связи",
    )
    await callback.answer()