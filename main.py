"""
main.py - Telegram Bot Entry Point
Production-ready bot with proper lifecycle management
"""
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from database import init_db, close_db, db
from handlers import router
from admin_handlers import admin_router
from middlewares import (
    ThrottlingMiddleware,
    LoggingMiddleware,
    DatabaseHealthMiddleware
)
from config import BOT_TOKEN, LOG_LEVEL, RATE_LIMIT, ADMIN_IDS

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    """Actions to perform on bot startup"""
    logger.info("Bot starting up...")
    
    # Initialize database
    await init_db()
    
    # Get bot info
    bot_info = await bot.get_me()
    logger.info(f"Bot started: @{bot_info.username} (ID: {bot_info.id})")
    
    # Get database stats
    stats = await db.get_stats()
    logger.info(f"Database ready: {stats['total_records']:,} records")
    
    # Log admin configuration
    logger.info(f"Configured admins: {len(ADMIN_IDS)} users")
    if not ADMIN_IDS or 123456789 in ADMIN_IDS:
        logger.warning("⚠️ WARNING: Default admin IDs detected! Please update config.py with your actual Telegram user ID")
        logger.warning("⚠️ Get your user ID from @userinfobot on Telegram")


async def on_shutdown(bot: Bot) -> None:
    """Actions to perform on bot shutdown"""
    logger.info("Bot shutting down...")
    
    # Close database
    await close_db()
    
    logger.info("Bot stopped")


async def main() -> None:
    """Main bot function"""
    
    # Validate bot token
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Please set your bot token in main.py")
        sys.exit(1)
    
    # Initialize bot with default properties
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )
    
    # Initialize dispatcher
    dp = Dispatcher()
    
    # Register middlewares (order matters!)
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(DatabaseHealthMiddleware(db))
    dp.message.middleware(ThrottlingMiddleware(rate_limit=RATE_LIMIT))
    
    # Register routers (admin router MUST be registered first for priority)
    dp.include_router(admin_router)
    dp.include_router(router)
    
    # Register startup/shutdown hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Start polling
    try:
        logger.info("Starting bot polling...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
