"""
Telegram bot implementation for RememBot with simplified interface.
"""

import asyncio
import logging
from typing import Optional
import json
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application, 
    MessageHandler, 
    CommandHandler, 
    ContextTypes,
    filters
)
from telegram.error import TelegramError, BadRequest, Conflict, Forbidden

from .database import DatabaseManager
from .content_processor import ContentProcessor, ContentProcessingError
from .classifier import ContentClassifier
from .query_handler import QueryHandler
from .config import get_config
from .health import HealthChecker
from .embeddings import EmbeddingsManager

logger = logging.getLogger(__name__)


class RememBot:
    """Main Telegram bot class with simplified interface."""
    
    def __init__(self, token: str, db_manager: DatabaseManager):
        """Initialize RememBot."""
        self.token = token
        self.db_manager = db_manager
        self.config = get_config()
        self.content_processor = ContentProcessor()
        self.classifier = ContentClassifier()
        self.query_handler = QueryHandler(db_manager)
        self.health_checker = HealthChecker(db_manager)
        # EmbeddingsManager is not used in the first phase (similarity features disabled)
        self.embeddings_manager = None
        
        # Create application
        self.application = Application.builder().token(token).build()
        
        # Add error handler
        self.application.add_error_handler(self._error_handler)
        
        # Add handlers
        self._setup_handlers()
    
    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors that occur during bot operation."""
        error = context.error
        
        # Log the error
        if isinstance(error, TelegramError):
            if isinstance(error, BadRequest):
                logger.warning(f"Bad request error: {error}")
            elif isinstance(error, Forbidden):
                logger.warning(f"Forbidden error (user may have blocked bot): {error}")
            elif isinstance(error, Conflict):
                logger.error(f"Conflict error (another instance running?): {error}")
            else:
                logger.error(f"Telegram error: {error}")
        else:
            logger.error(f"Unexpected error: {error}", exc_info=True)
        
        # Try to notify user if possible
        if update and hasattr(update, 'effective_chat'):
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Sorry, I encountered an error processing your request. Please try again later."
                )
            except Exception as e:
                logger.error(f"Failed to send error message to user: {e}")
    
    def _setup_handlers(self):
        """Set up message and command handlers."""
        # Command handlers - simplified to only essential commands
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("web", self.web_command))
        
        # Message handlers for content ingestion
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "🤖 **RememBot - Your Personal Knowledge Assistant**\n\n"
            "**How it works:**\n"
            "• Share any content with me (URLs, images, documents, text)\n"
            "• I'll store everything silently for you\n" 
            "• Use /web to access your personal knowledge base\n\n"
            "**Available Commands:**\n"
            "/help - Show this help message\n"
            "/web - Get link to your web interface\n\n"
            "**What I can store:**\n"
            "• 📄 Text messages and notes\n"
            "• 🔗 URLs and web pages  \n"
            "• 🖼️ Images (with text extraction)\n"
            "• 📁 Documents (PDF, Word, Excel, etc.)\n"
            "• 🎵 Voice notes and audio files\n\n"
            "Just share anything with me using Telegram's Share feature!\n"
            "Everything is stored locally and privately on your system."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def web_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /web command - generate secure web interface link."""
        user_id = update.effective_user.id
        
        try:
            # Generate a secure token for web authentication
            import secrets
            import time
            
            # Create a session token that expires in 24 hours
            token = secrets.token_urlsafe(32)
            expiry = int(time.time() + 24 * 3600)  # 24 hours from now
            
            # Store the token in database for validation
            await self.db_manager.store_web_token(user_id, token, expiry)
            
            # Generate the web interface URL
            web_url = f"http://localhost:8000/auth?token={token}&user_id={user_id}&expires={expiry}"
            
            response_text = (
                "🌐 **Access Your Knowledge Base**\n\n"
                f"Click here to access your web interface:\n"
                f"{web_url}\n\n"
                "⏰ This link expires in 24 hours\n"
                "🔒 Secure access to your personal data\n\n"
                "In the web interface you can:\n"
                "• Browse all your stored content\n"
                "• Search through everything\n" 
                "• Organize and manage your knowledge\n"
                "• View AI summaries and insights"
            )
            
            await update.message.reply_text(response_text, parse_mode='Markdown')
            logger.info(f"Generated web access token for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error generating web token for user {user_id}: {e}")
            await update.message.reply_text(
                "❌ Unable to generate web access link. Please try again later."
            )
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (URLs and plain text) - store for background processing."""
        user_id = update.effective_user.id
        text = update.message.text.strip()

        # Ignore messages that are exactly a 4-digit PIN (for web authentication)
        if text.isdigit() and len(text) == 4:
            # Reply with Telegram user ID for web authentication
            await update.message.reply_text(f"Your Telegram user ID: {user_id}", quote=False)
            # Link PIN to Telegram user ID via web API
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "http://localhost:8000/api/link_pin",
                        data={"pin": text, "telegram_user_id": str(user_id)}
                    )
                logger.info(f"Linked PIN {text} to Telegram user {user_id} via web API")
            except Exception as e:
                logger.warning(f"Failed to link PIN {text} to Telegram user {user_id}: {e}")
            logger.info(f"Ignored 4-digit PIN from user {user_id} (for web auth)")
            return

        try:
            # Detect content type
            content_type = 'url' if any(self.content_processor._is_url(word) for word in text.split()) else 'text'
            
            # Store content with pending status for background processing
            item_id = await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=text,
                content_type=content_type,
                parse_status='pending'
            )
            
            # Send simple confirmation
            if content_type == 'url':
                await update.message.reply_text("🔗 URL saved for processing", quote=False)
            else:
                await update.message.reply_text("📝 Text saved for processing", quote=False)
            
            logger.info(f"Stored {content_type} content as item {item_id} for user {user_id} (pending processing)")

        except Exception as e:
            logger.error(f"Error storing content for user {user_id}: {e}")
            await update.message.reply_text("❌ Failed to save content. Please try again later.", quote=False)
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages - store for background processing."""
        user_id = update.effective_user.id
        photo = update.message.photo[-1]  # Get highest resolution
        
        try:
            # Validate file size
            if photo.file_size > self.config.max_file_size_mb * 1024 * 1024:
                await update.message.reply_text(
                    f"❌ Image too large ({photo.file_size / 1024 / 1024:.1f}MB). "
                    f"Maximum size: {self.config.max_file_size_mb}MB",
                    quote=False
                )
                return
            
            # Store image reference for background processing
            item_id = await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=f"Photo: {photo.file_id}",
                content_type="image",
                metadata=json.dumps({
                    'file_id': photo.file_id,
                    'file_size': photo.file_size,
                    'width': photo.width,
                    'height': photo.height
                }),
                parse_status='pending'
            )
            
            await update.message.reply_text("📷 Image saved for processing", quote=False)
            logger.info(f"Stored image as item {item_id} for user {user_id} (pending processing)")
            
        except Exception as e:
            logger.error(f"Error storing image for user {user_id}: {e}")
            await update.message.reply_text("❌ Failed to save image. Please try again later.", quote=False)
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document messages - store for background processing."""
        user_id = update.effective_user.id
        document = update.message.document
        
        try:
            # Validate file size
            if document.file_size > self.config.max_file_size_mb * 1024 * 1024:
                await update.message.reply_text(
                    f"❌ Document too large ({document.file_size / 1024 / 1024:.1f}MB). "
                    f"Maximum size: {self.config.max_file_size_mb}MB",
                    quote=False
                )
                return
            
            # Store document reference for background processing
            item_id = await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=f"Document: {document.file_name}",
                content_type="document",
                metadata=json.dumps({
                    'file_id': document.file_id,
                    'file_name': document.file_name,
                    'file_size': document.file_size,
                    'mime_type': document.mime_type
                }),
                parse_status='pending'
            )
            
            await update.message.reply_text(f"📄 Document '{document.file_name}' saved for processing", quote=False)
            logger.info(f"Stored document as item {item_id} for user {user_id} (pending processing)")
            
        except Exception as e:
            logger.error(f"Error storing document for user {user_id}: {e}")
            await update.message.reply_text("❌ Failed to save document. Please try again later.", quote=False)
    
    async def startup(self, application):
        """Initialize services on startup."""
        try:
            await self.health_checker.start()
            logger.info("Health checker started")
        except Exception as e:
            logger.warning(f"Failed to start health checker: {e}")
    
    async def shutdown(self, application):
        """Cleanup services on shutdown."""
        try:
            await self.content_processor.close()
            await self.health_checker.stop()
            logger.info("Services shut down cleanly")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def run(self):
        """Run the bot using long polling with enhanced configuration."""
        logger.info("Starting RememBot with long polling...")
        
        # Set up startup and shutdown handlers
        self.application.post_init = self.startup
        self.application.post_shutdown = self.shutdown
        
        # Start polling with configurable parameters
        self.application.run_polling(
            poll_interval=1.0,
            timeout=20,
            bootstrap_retries=self.config.max_retries
        )