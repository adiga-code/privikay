import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import settings
from database.models import DailyLog, GroupMember, SupportGroup, User, WeightGoal
from heroes.data import get_hero
from keyboards.builders import (
    kb_academy, kb_feedback_useful, kb_start_checkin, kb_start_weight, kb_support_friends,
)
from services.analytics_service import AnalyticsService
from services.log_service import LogService
from services.report_service import ReportService
from services.subscription_service import SubscriptionService
from services.user_service import UserService

logger = logging.getLogger(__name__)


def setup_scheduler(bot: Bot, session_maker: async_sessionmaker) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # Every minute: daily check-in reminders + sleep reminders
    scheduler.add_job(
        send_minute_reminders,
        CronTrigger(minute="*"),
        args=[bot, session_maker],
        id="minute_reminders",
        replace_existing=True,
    )

    # Once per day at 00:05 UTC: weekly reports, weight checks, insights, academy
    scheduler.add_job(
        run_daily_maintenance,
        CronTrigger(hour=0, minute=5),
        args=[bot, session_maker],
        id="daily_maintenance",
        replace_existing=True,
    )

    # Group reports at 18:00 UTC (21:00 Moscow time)
    scheduler.add_job(
        send_group_reports,
        CronTrigger(hour=18, minute=0),
        args=[bot, session_maker],
        id="group_reports",
        replace_existing=True,
    )

    return scheduler


# ── Every-minute tasks ────────────────────────────────────────────────────────

async def send_minute_reminders(bot: Bot, session_maker: async_sessionmaker) -> None:
    now = datetime.now(timezone.utc)
    current_time = now.strftime("%H:%M")

    # Time 30 min earlier (for sleep reminder)
    reminder_time_utc = (now + timedelta(minutes=30)).strftime("%H:%M")

    async with session_maker() as session:
        result = await session.execute(
            select(User).where(User.onboarding_done.is_(True))
        )
        users: list[User] = list(result.scalars().all())

        sub_svc = SubscriptionService()
        log_svc = LogService(session)

        for user in users:
            # Skip expired/inactive users
            if not sub_svc.is_active(user):
                continue

            hero = get_hero(user.hero_key)

            # 1. Daily check-in reminder
            if user.checkin_time == current_time:
                try:
                    log = await log_svc.get_today_log(user.id)
                    if not log or log.day_index is None:
                        await bot.send_message(
                            user.id,
                            f"{hero.phrase('greeting')}\n\n"
                            f"📋 Время отметить привычки!",
                            parse_mode="Markdown",
                            reply_markup=kb_start_checkin(),
                        )
                except Exception as e:
                    logger.warning("Checkin reminder failed user=%s: %s", user.id, e)

            # 2. Sleep reminder (30 min before bedtime, only if sleep habit selected)
            if (
                user.sleep_target_time
                and user.sleep_target_time == reminder_time_utc
                and "sleep" in user.selected_habits
            ):
                try:
                    await bot.send_message(
                        user.id,
                        f"🌙 {hero.phrase('sleep')}",
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.warning("Sleep reminder failed user=%s: %s", user.id, e)


# ── Daily maintenance ─────────────────────────────────────────────────────────

async def run_daily_maintenance(bot: Bot, session_maker: async_sessionmaker) -> None:
    async with session_maker() as session:
        user_svc = UserService(session)
        log_svc = LogService(session)
        analytics = AnalyticsService()
        report_svc = ReportService(analytics)
        sub_svc = SubscriptionService()

        users = await user_svc.get_all_active()

        for user in users:
            if not sub_svc.is_active(user):
                continue

            hero = get_hero(user.hero_key)
            today = date.today()

            try:
                days_since_reg = _days_since(None, today, since=user.registered_at.date())

                # 1. Weekly report (every 7 days)
                if _should_send_weekly_report(user, today):
                    from_date = today - timedelta(days=6)
                    logs = await log_svc.get_logs_between(user.id, from_date, today)
                    weight_logs = await log_svc.get_weight_logs(user.id)
                    report = report_svc.build_weekly_report(user, logs, weight_logs)

                    await bot.send_message(user.id, report, parse_mode="Markdown")

                    from aiogram.types import BufferedInputFile
                    from keyboards.builders import kb_share_report
                    from services.image_service import generate_progress_card
                    try:
                        img_bytes = generate_progress_card(user, logs, weight_logs, analytics)
                        await bot.send_photo(
                            user.id,
                            BufferedInputFile(img_bytes, filename="progress.png"),
                            caption="📸 *Карточка прогресса* — сохрани и поделись в сторис!",
                            parse_mode="Markdown",
                            reply_markup=kb_share_report(),
                        )
                    except Exception as img_err:
                        logger.warning("Image generation failed user=%s: %s", user.id, img_err)
                        card = report_svc.build_progress_card(user, logs)
                        await bot.send_message(
                            user.id,
                            f"📋 *Карточка прогресса:*\n\n{card}",
                            parse_mode="Markdown",
                            reply_markup=kb_share_report(),
                        )
                    await user_svc.update(user, last_weekly_report=today)

                # 2. Weekly weight reminder
                if (
                    user.weight_goal != WeightGoal.NONE
                    and _days_since(user.last_weight_check, today) >= 7
                ):
                    await bot.send_message(
                        user.id,
                        f"⚖️ Сегодня день контрольного взвешивания!\n\n"
                        f"{hero.phrase('greeting')}",
                        parse_mode="Markdown",
                        reply_markup=kb_start_weight(),
                    )

                # 3. Insights (every 4 days)
                if _days_since(user.last_insight_sent, today) >= 4:
                    all_logs = await log_svc.get_all_logs(user.id)
                    insights = analytics.get_insights(all_logs)
                    if insights:
                        await bot.send_message(
                            user.id,
                            f"💡 *Наблюдение:*\n\n{insights[0]}",
                            parse_mode="Markdown",
                        )
                        await user_svc.update(user, last_insight_sent=today)

                # 4. Academy offer (once, after 7+ days)
                if (
                    not user.academy_offered
                    and _days_since(None, today, since=user.registered_at.date()) >= 7
                ):
                    await bot.send_message(
                        user.id,
                        f"{hero.emoji} *Вы уже формируете полезные привычки!*\n\n"
                        "Следующий шаг — регулярное движение. "
                        "Оно улучшает энергию, сон и снижает стресс.",
                        parse_mode="Markdown",
                        reply_markup=kb_academy(settings.academy_url),
                    )
                    await user_svc.update(user, academy_offered=True)

                # 5. Referral offer after 3-day streak (only once)
                if (
                    user.last_referral_offer_sent != today
                    and not user.referral_reward_given
                ):
                    all_logs = await log_svc.get_all_logs(user.id)
                    sorted_logs = sorted(all_logs, key=lambda l: l.date, reverse=True)
                    streak = 0
                    for lg in sorted_logs:
                        if lg.day_index is not None:
                            streak += 1
                        else:
                            break
                    if streak >= 3:
                        from aiogram.types import BufferedInputFile
                        bot_info = await bot.get_me()
                        link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
                        await bot.send_message(
                            user.id,
                            f"🔥 Ты держишь привычку уже *{streak} дня подряд*!\n\n"
                            "Многие проходят челлендж вместе с друзьями — так легче не срываться.\n\n"
                            "Пригласи *3 друзей* и получи бонус — *21 день подписки бесплатно*.\n\n"
                            f"Твоя ссылка:\n`{link}`",
                            parse_mode="Markdown",
                            reply_markup=kb_support_friends(),
                        )
                        await user_svc.update(user, last_referral_offer_sent=today)

                # 6. Open free-text feedback (at day 7)
                if (
                    days_since_reg == 7
                    and user.last_open_feedback_sent != today
                ):
                    from keyboards.builders import kb_feedback_entry
                    await bot.send_message(
                        user.id,
                        "И ещё один маленький вопрос 🙏\n\n"
                        "*Нам очень важна твоя обратная связь на этом этапе.*\n\n"
                        "Напиши, пожалуйста:\n"
                        "— что тебе нравится в боте\n"
                        "— что не нравится\n"
                        "— что хотелось бы добавить или изменить\n\n"
                        "Можно коротко или подробно — как удобно.\n"
                        "Мы всё читаем и готовы улучшать продукт вместе с вами.",
                        parse_mode="Markdown",
                        reply_markup=kb_feedback_entry(),
                    )
                    await user_svc.update(user, last_open_feedback_sent=today)

                # 7. Beta feedback (at days 5, 10, 15 of trial)
                if (
                    days_since_reg in (5, 10, 15)
                    and user.last_feedback_sent != today
                ):
                    ordinal = {5: "первые 5", 10: "10", 15: "15"}[days_since_reg]
                    await bot.send_message(
                        user.id,
                        f"📋 *{ordinal} дней с Привыкаем!*\n\n"
                        f"Пара вопросов — займёт 30 секунд. "
                        f"Твой отзыв поможет сделать бота лучше 🙏\n\n"
                        f"*Бот оказался полезным?*",
                        parse_mode="Markdown",
                        reply_markup=kb_feedback_useful(days_since_reg),
                    )
                    await user_svc.update(user, last_feedback_sent=today)

            except Exception as e:
                logger.warning("Maintenance error user=%s: %s", user.id, e)


# ── Group daily reports ────────────────────────────────────────────────────────

async def send_group_reports(bot: Bot, session_maker: async_sessionmaker) -> None:
    from sqlalchemy import select as sa_select
    today = date.today()

    async with session_maker() as session:
        groups_result = await session.execute(
            sa_select(SupportGroup).where(
                (SupportGroup.last_report_sent == None) | (SupportGroup.last_report_sent < today)
            )
        )
        groups: list[SupportGroup] = list(groups_result.scalars().all())

        log_svc = LogService(session)
        user_svc = UserService(session)

        for group in groups:
            try:
                members_result = await session.execute(
                    sa_select(GroupMember).where(GroupMember.group_id == group.id)
                )
                members = list(members_result.scalars().all())
                if len(members) < 2:
                    continue

                # Load users and their common habits
                users = []
                for m in members:
                    u = await user_svc.get(m.user_id)
                    if u:
                        users.append(u)

                if not users:
                    continue

                # Find common habits
                from habits.registry import HABIT_REGISTRY
                common = set(users[0].selected_habits)
                for u in users[1:]:
                    common &= set(u.selected_habits)
                common = [h for h in common if h in HABIT_REGISTRY]

                if not common:
                    continue

                # Build report lines
                lines = ["👥 *Ваша группа поддержки сегодня:*\n"]
                all_done = True
                for u in users:
                    log = await log_svc.get_today_log(u.id)
                    if not log:
                        all_done = False
                        lines.append(f"• {u.name} — не отметил сегодня")
                        continue
                    from services.analytics_service import AnalyticsService
                    analytics = AnalyticsService()
                    done = sum(
                        1 for h in common
                        if analytics._get_value(log, h) is not None
                        and HABIT_REGISTRY[h].evaluate(
                            analytics._get_value(log, h),
                            analytics._get_target(u, h)
                        ).status == "done"
                    )
                    if done < len(common):
                        all_done = False
                    lines.append(f"• {u.name} — {done} из {len(common)}")

                # Update streak
                if all_done:
                    group.streak = (group.streak or 0) + 1
                    lines.append(f"\n🔥 *Общая серия группы: {group.streak} дн.*\nПродолжаем завтра!")
                else:
                    group.streak = 0
                    lines.append("\n😔 Сегодня серия остановилась.\nЗавтра можно начать новую!")

                group.last_report_sent = today
                await session.commit()

                report_text = "\n".join(lines)
                for u in users:
                    try:
                        await bot.send_message(u.id, report_text, parse_mode="Markdown")
                    except Exception as e:
                        logger.warning("Group report failed user=%s: %s", u.id, e)

            except Exception as e:
                logger.warning("Group report error group=%s: %s", group.id, e)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _should_send_weekly_report(user: User, today: date) -> bool:
    if user.last_weekly_report is None:
        return (today - user.registered_at.date()).days >= 7
    return (today - user.last_weekly_report).days >= 7


def _days_since(last: date | None, today: date, since: date | None = None) -> int:
    ref = last or since
    return 999 if ref is None else (today - ref).days