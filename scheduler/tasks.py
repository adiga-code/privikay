import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import settings
from database.models import User, WeightGoal
from heroes.data import get_hero
from keyboards.builders import kb_academy, kb_feedback_useful, kb_start_checkin, kb_start_weight
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

                # 5. Beta feedback (at days 5, 10, 15 of trial)
                days_since_reg = _days_since(None, today, since=user.registered_at.date())
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _should_send_weekly_report(user: User, today: date) -> bool:
    if user.last_weekly_report is None:
        return (today - user.registered_at.date()).days >= 7
    return (today - user.last_weekly_report).days >= 7


def _days_since(last: date | None, today: date, since: date | None = None) -> int:
    ref = last or since
    return 999 if ref is None else (today - ref).days