import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Time settings
os.environ['TZ'] = 'Europe/Kyiv'
if hasattr(os, 'tzset'):
    os.tzset()

# Bot settings
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
URL_PAGE = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"

# Database settings
DATABASE_PATH = os.getenv("DATABASE_PATH", "users.db")

# Cache settings
CACHE_PATH = os.getenv("CACHE_PATH", "cache/cached_schedules.json")

# Logging settings
LOGS_PATH = os.getenv("LOGS_PATH", "logs/")

# Queue settings
QUEUES = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16"]

# Time settings
TIMEZONE = "Europe/Kyiv"