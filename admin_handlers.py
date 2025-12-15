"""
admin_handlers.py - Admin-Only Commands & File Upload Import
Allows admins to import data directly through Telegram
"""
import logging
import os
import tempfile
from pathlib import Path
from aiogram import Router, F
from aiogram.types import Message, Document
from aiogram.filters import Command
from aiogram.enums import ParseMode

from database import db
from filters import IsAdminFilter, IsNotAdminFilter
from config import MAX_FILE_SIZE_MB, ALLOWED_FILE_EXTENSIONS, CHUNK_SIZE
from importer import LogImporter

logger = logging.getLogger(__name__)

# Create admin router
admin_router = Router()


@admin_router.message(Command("admin"), IsAdminFilter())
async def cmd_admin_panel(message: Message) -> None:
    """Show admin panel and available commands"""
    admin_text = (
        "🔐 <b>Admin Panel</b>\n\n"
        "<b>Available Commands:</b>\n"
        "• <code>/import</code> - Upload a file to import\n"
        "• <code>/clear_db</code> - Clear all database records\n"
        "• <code>/stats</code> - View database statistics\n"
        "• <code>/admin</code> - Show this panel\n\n"
        "<b>File Import:</b>\n"
        "Just send me a .txt, .log, or .csv file and I'll import it automatically!\n\n"
        f"📁 Max file size: <code>{MAX_FILE_SIZE_MB} MB</code>\n"
        f"📋 Allowed formats: <code>{', '.join(ALLOWED_FILE_EXTENSIONS)}</code>"
    )
    
    await message.answer(admin_text, parse_mode=ParseMode.HTML)


@admin_router.message(Command("admin"), IsNotAdminFilter())
async def cmd_admin_denied(message: Message) -> None:
    """Handle non-admin users trying to access admin panel"""
    await message.answer(
        "❌ <b>Access Denied</b>\n\n"
        "This command is only available to administrators.\n"
        f"Your user ID: <code>{message.from_user.id}</code>",
        parse_mode=ParseMode.HTML
    )


@admin_router.message(Command("import"), IsAdminFilter())
async def cmd_import(message: Message) -> None:
    """Instruct admin to upload a file"""
    await message.answer(
        "📁 <b>File Import</b>\n\n"
        "Please send me a file to import.\n\n"
        "<b>Supported formats:</b>\n"
        f"• {', '.join(ALLOWED_FILE_EXTENSIONS)}\n\n"
        f"<b>Max size:</b> {MAX_FILE_SIZE_MB} MB\n\n"
        "The import will start automatically when you send the file.",
        parse_mode=ParseMode.HTML
    )


@admin_router.message(Command("clear_db"), IsAdminFilter())
async def cmd_clear_db(message: Message) -> None:
    """Clear all database records (dangerous operation)"""
    # Get current stats before clearing
    stats = await db.get_stats()
    total_records = stats.get('total_records', 0)
    
    if total_records == 0:
        await message.answer("ℹ️ Database is already empty.")
        return
    
    # Ask for confirmation
    await message.answer(
        f"⚠️ <b>WARNING: DESTRUCTIVE OPERATION</b>\n\n"
        f"This will permanently delete <b>{total_records:,}</b> records!\n\n"
        f"To confirm, send: <code>/confirm_clear</code>\n"
        f"To cancel, just ignore this message.",
        parse_mode=ParseMode.HTML
    )


@admin_router.message(Command("confirm_clear"), IsAdminFilter())
async def cmd_confirm_clear(message: Message) -> None:
    """Confirm and execute database clear"""
    status_msg = await message.answer("🗑️ Clearing database...")
    
    try:
        await db.clear_all()
        await status_msg.edit_text(
            "✅ <b>Database cleared successfully!</b>\n\n"
            "All records have been permanently deleted.",
            parse_mode=ParseMode.HTML
        )
        logger.warning(f"Database cleared by admin {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        await status_msg.edit_text(
            f"❌ <b>Error clearing database:</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )


@admin_router.message(F.document, IsAdminFilter())
async def handle_file_upload(message: Message) -> None:
    """Handle file uploads from admins for import"""
    document: Document = message.document
    
    # Check file extension
    file_ext = Path(document.file_name).suffix.lower()
    if file_ext not in ALLOWED_FILE_EXTENSIONS:
        await message.answer(
            f"❌ <b>Invalid file type!</b>\n\n"
            f"Allowed formats: {', '.join(ALLOWED_FILE_EXTENSIONS)}\n"
            f"Your file: <code>{file_ext}</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Check file size
    file_size_mb = document.file_size / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        await message.answer(
            f"❌ <b>File too large!</b>\n\n"
            f"Max size: <code>{MAX_FILE_SIZE_MB} MB</code>\n"
            f"Your file: <code>{file_size_mb:.2f} MB</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Send processing message
    status_msg = await message.answer(
        f"📥 <b>Downloading file...</b>\n\n"
        f"File: <code>{document.file_name}</code>\n"
        f"Size: <code>{file_size_mb:.2f} MB</code>",
        parse_mode=ParseMode.HTML
    )
    
    # Download file to temporary location
    temp_dir = tempfile.mkdtemp()
    temp_file_path = Path(temp_dir) / document.file_name
    
    try:
        # Download file
        await message.bot.download(document, destination=temp_file_path)
        
        logger.info(f"File downloaded: {document.file_name} ({file_size_mb:.2f} MB)")
        
        # Update status
        await status_msg.edit_text(
            f"⚙️ <b>Processing file...</b>\n\n"
            f"File: <code>{document.file_name}</code>\n"
            f"This may take a few minutes for large files...",
            parse_mode=ParseMode.HTML
        )
        
        # Import file
        importer = LogImporter(db, chunk_size=CHUNK_SIZE)
        stats = await importer.import_file(temp_file_path, deduplicate=True)
        
        # Calculate metrics
        duration = (stats["end_time"] - stats["start_time"]).total_seconds()
        records_per_second = stats["imported"] / duration if duration > 0 else 0
        
        # Send success message
        success_text = (
            f"✅ <b>Import Complete!</b>\n\n"
            f"📄 File: <code>{document.file_name}</code>\n"
            f"📊 Records imported: <code>{stats['imported']:,}</code>\n"
            f"🔄 Duplicates skipped: <code>{stats['duplicates']:,}</code>\n"
            f"⏱️ Duration: <code>{duration:.1f}s</code>\n"
            f"⚡ Speed: <code>{records_per_second:,.0f} records/sec</code>\n\n"
        )
        
        # Get updated database stats
        db_stats = await db.get_stats()
        success_text += (
            f"💾 <b>Database Status:</b>\n"
            f"Total records: <code>{db_stats['total_records']:,}</code>\n"
            f"Database size: <code>{db_stats['db_size_mb']} MB</code>"
        )
        
        await status_msg.edit_text(success_text, parse_mode=ParseMode.HTML)
        
        logger.info(
            f"Import completed by admin {message.from_user.id}: "
            f"{stats['imported']:,} records in {duration:.1f}s"
        )
        
    except Exception as e:
        logger.error(f"Error importing file {document.file_name}: {e}")
        await status_msg.edit_text(
            f"❌ <b>Import Failed</b>\n\n"
            f"Error: <code>{str(e)}</code>\n\n"
            f"Please check the file format and try again.",
            parse_mode=ParseMode.HTML
        )
    
    finally:
        # Clean up temporary file
        try:
            if temp_file_path.exists():
                temp_file_path.unlink()
            if Path(temp_dir).exists():
                Path(temp_dir).rmdir()
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")


@admin_router.message(F.document, IsNotAdminFilter())
async def handle_file_upload_denied(message: Message) -> None:
    """Handle file uploads from non-admin users"""
    await message.answer(
        "❌ <b>Access Denied</b>\n\n"
        "Only administrators can import files.\n"
        "Please contact an admin if you need to add data.",
        parse_mode=ParseMode.HTML
    )


# Add info message for text files in regular chat
@admin_router.message(F.text.contains(".txt") | F.text.contains(".log"), IsNotAdminFilter())
async def handle_file_mention(message: Message) -> None:
    """Inform users about admin-only import feature"""
    if any(cmd in message.text.lower() for cmd in ['import', 'upload', 'add data']):
        await message.answer(
            "ℹ️ File imports are available for administrators only.\n"
            "Contact an admin if you need to import data."
        )
