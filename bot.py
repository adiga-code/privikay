import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import settings
from database.engine import create_db, session_maker
from database.middleware import DatabaseMiddleware
from database.subscription_middleware import SubscriptionMiddleware
from handlers.admin import admin_router
from handlers.checkin import checkin_router
from handlers.feedback import feedback_router
from handlers.groups import groups_router
from handlers.onboarding import onboarding_router
from handlers.referral import referral_router
from handlers.settings import settings_router
from handlers.start import start_router
from handlers.subscription import subscription_router
from handlers.weight import weight_router
from scheduler.tasks import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await create_db()
    logger.info("Database ready.")

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Middleware order matters:
    # 1. DatabaseMiddleware → injects session into data{}
    # 2. SubscriptionMiddleware → uses session to check subscription
    dp.update.middleware(DatabaseMiddleware(session_maker))
    dp.update.middleware(SubscriptionMiddleware())

    # Routers — order defines handler priority
    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(subscription_router)
    dp.include_router(feedback_router)
    dp.include_router(referral_router)
    dp.include_router(groups_router)
    dp.include_router(onboarding_router)
    dp.include_router(settings_router)
    dp.include_router(weight_router)
    dp.include_router(checkin_router)

    await bot.set_my_commands([
        BotCommand(command="checkin",   description="Отметить привычки за сегодня"),
        BotCommand(command="report",    description="Отчёт за последние 7 дней"),
        BotCommand(command="weight",    description="Записать вес"),
        BotCommand(command="subscribe", description="Подписка — 249 ₽/мес или 1790 ₽/год"),
        BotCommand(command="referral",  description="Пригласить друзей и получить бонус"),
        BotCommand(command="groups",    description="Группы поддержки"),
        BotCommand(command="feedback",  description="Оставить отзыв о боте"),
        BotCommand(command="settings",  description="Настройки: герой, время, часовой пояс"),
        BotCommand(command="help",      description="Справка"),
        BotCommand(command="start",     description="Перезапустить бота"),
    ])
    logger.info("Bot commands set.")

    scheduler = setup_scheduler(bot, session_maker)
    scheduler.start()
    logger.info("Scheduler started.")

    try:
        logger.info("Bot polling started.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())