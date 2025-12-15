"""
handlers.py - Telegram Bot Command Handlers
Implements all bot commands and search functionality
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from typing import Optional

from database import db

logger = logging.getLogger(__name__)

# Create router
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start command"""
    welcome_text = (
        "🔍 <b>Welcome to the Log Search Bot!</b>\n\n"
        "I can search through millions of records in milliseconds.\n\n"
        "<b>Commands:</b>\n"
        "• <code>/search [query]</code> - Search the database\n"
        "• <code>/stats</code> - View database statistics\n"
        "• <code>/help</code> - Show this help message\n\n"
        "<b>Quick Search:</b>\n"
        "Just send me any text, and I'll search for it!\n\n"
        "Example: <code>admin@example.com</code>"
    )
    
    await message.answer(welcome_text, parse_mode=ParseMode.HTML)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command"""
    help_text = (
        "📖 <b>How to Use This Bot</b>\n\n"
        "<b>Search Methods:</b>\n"
        "1. <code>/search your query here</code>\n"
        "2. Simply send any text message\n\n"
        "<b>Search Tips:</b>\n"
        "• Use specific keywords for better results\n"
        "• Multiple words will search for any matching term\n"
        "• Results are ranked by relevance\n"
        "• Maximum 30 results per search\n\n"
        "<b>Examples:</b>\n"
        "• <code>username@domain.com</code>\n"
        "• <code>password123</code>\n"
        "• <code>API_KEY token</code>\n\n"
        "<b>Other Commands:</b>\n"
        "• <code>/stats</code> - Database statistics\n"
        "• <code>/help</code> - This message"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Handle /stats command - show database statistics"""
    try:
        stats = await db.get_stats()
        
        if "error" in stats:
            await message.answer(f"❌ Error retrieving stats: {stats['error']}")
            return
        
        stats_text = (
            "📊 <b>Database Statistics</b>\n\n"
            f"📝 Total Records: <code>{stats['total_records']:,}</code>\n"
            f"💾 Database Size: <code>{stats['db_size_mb']} MB</code>\n"
            f"📁 Database Path: <code>{stats['db_path']}</code>\n\n"
            f"⚡ Average search time: <code>&lt;100ms</code>"
        )
        
        await message.answer(stats_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await message.answer("❌ Failed to retrieve statistics. Please try again.")


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    """Handle /search command"""
    # Extract query from command
    query = message.text.replace("/search", "", 1).strip()
    
    if not query:
        await message.answer(
            "❌ Please provide a search query.\n"
            "Example: <code>/search admin@example.com</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    await perform_search(message, query)


@router.message(F.text)
async def handle_text(message: Message) -> None:
    """Handle any text message as a search query"""
    query = message.text.strip()
    
    # Ignore very short queries
    if len(query) < 2:
        await message.answer(
            "❌ Query too short. Please enter at least 2 characters."
        )
        return
    
    await perform_search(message, query)


async def perform_search(message: Message, query: str) -> None:
    """
    Perform database search and send results
    
    Args:
        message: Telegram message object
        query: Search query string
    """
    # Send "searching..." message
    status_msg = await message.answer("🔍 Searching database...")
    
    try:
        # Perform search
        results, total_count = await db.search(query, limit=30)
        
        # Delete status message
        await status_msg.delete()
        
        # Handle no results
        if total_count == 0:
            await message.answer(
                f"❌ No results found for: <code>{escape_html(query)}</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Format and send results
        await send_results(message, query, results, total_count)
        
    except Exception as e:
        logger.error(f"Search error for query '{query}': {e}")
        await status_msg.delete()
        await message.answer(
            "❌ An error occurred during search. Please try again."
        )


async def send_results(
    message: Message,
    query: str,
    results: list[str],
    total_count: int
) -> None:
    """
    Format and send search results to user
    
    Args:
        message: Telegram message object
        query: Original search query
        results: List of matching records
        total_count: Total number of matches
    """
    # Build header
    header = (
        f"✅ <b>Found {total_count:,} result(s)</b> for: "
        f"<code>{escape_html(query)}</code>\n\n"
    )
    
    if total_count > len(results):
        header += f"📋 Showing top {len(results)} results:\n\n"
    
    # Format results
    result_lines = []
    for idx, record in enumerate(results, 1):
        # Truncate very long lines
        display_record = record[:200] + "..." if len(record) > 200 else record
        result_lines.append(f"{idx}. <code>{escape_html(display_record)}</code>")
    
    # Combine header and results
    full_message = header + "\n".join(result_lines)
    
    # Add footer if there are more results
    if total_count > len(results):
        full_message += (
            f"\n\n📊 <i>+{total_count - len(results):,} more results available</i>"
        )
    
    # Split message if too long (Telegram limit: 4096 characters)
    if len(full_message) > 4000:
        # Send in chunks
        chunks = split_message(full_message, 4000)
        for chunk in chunks:
            await message.answer(chunk, parse_mode=ParseMode.HTML)
    else:
        await message.answer(full_message, parse_mode=ParseMode.HTML)


def escape_html(text: str) -> str:
    """Escape HTML special characters for safe display"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def split_message(text: str, max_length: int) -> list[str]:
    """
    Split long message into chunks without breaking HTML tags
    
    Args:
        text: Message text
        max_length: Maximum length per chunk
        
    Returns:
        List of message chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    for line in text.split("\n"):
        if len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk += line + "\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = line + "\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks
