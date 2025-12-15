"""
filters.py - Custom Filters for Bot Commands
Includes admin-only command filtering
"""
from aiogram.filters import Filter
from aiogram.types import Message
from typing import Union

from config import is_admin


class IsAdminFilter(Filter):
    """Filter to restrict commands to admin users only"""
    
    async def __call__(self, message: Message) -> bool:
        """Check if user is an admin"""
        return is_admin(message.from_user.id)


class IsNotAdminFilter(Filter):
    """Filter for non-admin users (for sending permission denied messages)"""
    
    async def __call__(self, message: Message) -> bool:
        """Check if user is NOT an admin"""
        return not is_admin(message.from_user.id)
