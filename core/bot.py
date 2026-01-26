import asyncio
import logging
from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Import settings
from config.settings import TOKEN

# Import database functions
from database import init_db

# Import handlers
from handlers import router as handlers_router

# Import monitoring
from utils.monitoring import monitor_job

# Import cache initialization
from utils.cache import initialize_cache, update_clock_time_hands

# Import global bot instance
from core.globals import bot

# Initialize components
logging.basicConfig(level=logging.INFO)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

async def main():
    """Main bot function"""
    # Initialize database
    init_db()

    # Register handlers
    dp.include_router(handlers_router)

    # Initialize cache with site data on startup
    await initialize_cache()

    # Start scheduler
    scheduler.add_job(monitor_job, 'interval', minutes=5)
    scheduler.add_job(update_clock_time_hands, 'interval', hours=1)
    scheduler.start()

    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())