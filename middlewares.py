"""
middlewares.py - Rate Limiting and Anti-Spam Middleware
Prevents database overload from user spam
"""
import time
import logging
from typing import Callable, Dict, Any, Awaitable
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """
    Rate limiting middleware to prevent spam
    Implements token bucket algorithm per user
    """
    
    def __init__(self, rate_limit: float = 1.0):
        """
        Args:
            rate_limit: Minimum seconds between requests per user
        """
        super().__init__()
        self.rate_limit = rate_limit
        self.user_timestamps: Dict[int, float] = {}
        self.user_warnings: Dict[int, int] = defaultdict(int)
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Middleware execution logic"""
        
        # Get user ID
        user_id = event.from_user.id if event.from_user else None
        
        if user_id is None:
            return await handler(event, data)
        
        current_time = time.time()
        last_time = self.user_timestamps.get(user_id, 0)
        time_passed = current_time - last_time
        
        # Check if user is rate limited
        if time_passed < self.rate_limit:
            self.user_warnings[user_id] += 1
            warnings = self.user_warnings[user_id]
            
            # Progressive warnings
            if warnings == 1:
                await event.answer(
                    "⚠️ Please slow down! Wait a moment before searching again."
                )
            elif warnings < 5:
                await event.answer(
                    f"⚠️ Rate limit exceeded ({warnings}x). "
                    f"Please wait {self.rate_limit:.1f} seconds between searches."
                )
            else:
                # Stricter message for repeated violations
                await event.answer(
                    "🚫 Too many requests! You've been temporarily throttled. "
                    "Please wait 10 seconds."
                )
            
            logger.warning(
                f"Rate limit hit by user {user_id}: "
                f"{time_passed:.2f}s passed (limit: {self.rate_limit}s), "
                f"warnings: {warnings}"
            )
            return
        
        # Reset warning counter on successful request
        if user_id in self.user_warnings:
            self.user_warnings[user_id] = 0
        
        # Update timestamp
        self.user_timestamps[user_id] = current_time
        
        # Continue to handler
        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    """Log all incoming requests for monitoring"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Log request details"""
        
        user = event.from_user
        if isinstance(event, Message):
            logger.info(
                f"Message from {user.id} (@{user.username}): "
                f"{event.text[:100] if event.text else '[no text]'}"
            )
        elif isinstance(event, CallbackQuery):
            logger.info(
                f"Callback from {user.id} (@{user.username}): {event.data}"
            )
        
        return await handler(event, data)


class DatabaseHealthMiddleware(BaseMiddleware):
    """Check database health before processing requests"""
    
    def __init__(self, db_instance):
        super().__init__()
        self.db = db_instance
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Verify database is accessible"""
        
        # Quick health check
        if not self.db._connection:
            logger.error("Database connection lost!")
            await event.answer(
                "❌ Database temporarily unavailable. Please try again in a moment."
            )
            return
        
        return await handler(event, data)
