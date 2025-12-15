"""
config.py - Bot Configuration & Admin Management
Centralized configuration with admin user management
"""
import os
from typing import Set
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Admin Configuration
# Add admin user IDs here (get your ID from @userinfobot on Telegram)
ADMIN_IDS: Set[int] = {
    123456789,  # Replace with actual admin user IDs
    987654321,
}

# You can also load admin IDs from environment variable
# Format: ADMIN_IDS=123456789,987654321
if env_admins := os.getenv("ADMIN_IDS"):
    ADMIN_IDS.update(int(uid.strip()) for uid in env_admins.split(",") if uid.strip())

# Database Configuration
DB_PATH = os.getenv("DB_PATH", "logs_database.db")

# Performance Configuration
RATE_LIMIT = float(os.getenv("RATE_LIMIT", "1.0"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "10000"))
SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT", "30"))

# File Upload Configuration
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))  # Max file size for upload
ALLOWED_FILE_EXTENSIONS = {".txt", ".log", ".csv"}

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    return user_id in ADMIN_IDS


def add_admin(user_id: int) -> None:
    """Add a new admin"""
    ADMIN_IDS.add(user_id)


def remove_admin(user_id: int) -> None:
    """Remove an admin"""
    ADMIN_IDS.discard(user_id)
