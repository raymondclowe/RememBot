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
        """Handle text messages (URLs and plain text) with enhanced error handling."""
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

        # Send processing indicator for longer operations
        is_url = any(self.content_processor._is_url(word) for word in text.split())
        if is_url:
            await update.message.reply_text("🔄 Processing URL...", quote=False)

        try:
            # Process the content
            processed_content = await self.content_processor.process_text(text)

            # Classify the content if extraction was successful
            taxonomy = None
            if not processed_content.get('metadata', {}).get('error'):
                try:
                    taxonomy = await self.classifier.classify_content(processed_content['extracted_info'])
                except Exception as e:
                    logger.warning(f"Classification failed for user {user_id}: {e}")
                    taxonomy = {'error': str(e)}

            # Store in database with processing time
            processing_time = processed_content.get('metadata', {}).get('processing_time_ms')
            item_id = await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=text,
                content_type=processed_content['content_type'],
                metadata=json.dumps(processed_content['metadata']),
                extracted_info=processed_content['extracted_info'],
                taxonomy=json.dumps(taxonomy) if taxonomy else None,
                processing_time_ms=processing_time
            )

            # Generate embedding asynchronously (don't wait for completion) - disabled for now
            # if processed_content['extracted_info'] and processed_content['extracted_info'].strip():
            #     asyncio.create_task(
            #         self.embeddings_manager.store_embedding(
            #             item_id, processed_content['extracted_info']
            #         )
            #     )

            # Send success feedback for errors or notable processing
            if processed_content.get('metadata', {}).get('error'):
                await update.message.reply_text(
                    f"⚠️ Content stored with processing issues: {processed_content['metadata']['error'][:100]}",
                    quote=False
                )
            elif is_url and processed_content['content_type'] == 'url':
                title = processed_content.get('metadata', {}).get('title', 'Unknown')
                await update.message.reply_text(f"✅ Saved: {title}", quote=False)

            logger.info(f"Processed text content for user {user_id} ({processed_content['content_type']})")

        except ContentProcessingError as e:
            logger.warning(f"Content processing error for user {user_id}: {e}")
            await update.message.reply_text(f"⚠️ {str(e)}", quote=False)
        except Exception as e:
            logger.error(f"Error processing text for user {user_id}: {e}")
            await update.message.reply_text("❌ Failed to process content. Please try again later.", quote=False)
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages with enhanced error handling."""
        user_id = update.effective_user.id
        photo = update.message.photo[-1]  # Get highest resolution
        
        # Send processing indicator
        processing_msg = await update.message.reply_text("🔄 Processing image with OCR...", quote=False)
        
        try:
            # Validate file size before processing
            if photo.file_size > self.config.max_file_size_mb * 1024 * 1024:
                await processing_msg.edit_text(
                    f"❌ Image too large ({photo.file_size / 1024 / 1024:.1f}MB). "
                    f"Maximum size: {self.config.max_file_size_mb}MB"
                )
                return
            
            # Get file
            file = await context.bot.get_file(photo.file_id)
            
            # Process the image
            processed_content = await self.content_processor.process_image(file)
            
            # Classify the content if OCR was successful
            taxonomy = None
            if not processed_content.get('metadata', {}).get('error'):
                try:
                    if processed_content.get('metadata', {}).get('has_text'):
                        taxonomy = await self.classifier.classify_content(processed_content['extracted_info'])
                except Exception as e:
                    logger.warning(f"Classification failed for user {user_id}: {e}")
                    taxonomy = {'error': str(e)}
            
            # Store in database with processing time
            processing_time = processed_content.get('metadata', {}).get('processing_time_ms')
            item_id = await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=f"Photo: {photo.file_id}",
                content_type="image",
                metadata=json.dumps(processed_content['metadata']),
                extracted_info=processed_content['extracted_info'],
                taxonomy=json.dumps(taxonomy) if taxonomy else None,
                processing_time_ms=processing_time
            )
            
            # Generate embedding for OCR text if available - disabled for now
            # if (processed_content.get('metadata', {}).get('has_text') and 
            #     processed_content['extracted_info'] and 
            #     processed_content['extracted_info'].strip()):
            #     asyncio.create_task(
            #         self.embeddings_manager.store_embedding(
            #             item_id, processed_content['extracted_info']
            #         )
            #     )
            
            # Update processing message with result
            if processed_content.get('metadata', {}).get('error'):
                await processing_msg.edit_text(f"⚠️ Image stored with processing issues: {processed_content['metadata']['error'][:100]}")
            elif processed_content.get('metadata', {}).get('has_text'):
                ocr_length = processed_content.get('metadata', {}).get('ocr_length', 0)
                await processing_msg.edit_text(f"✅ Image processed - extracted {ocr_length} characters of text")
            else:
                await processing_msg.edit_text("✅ Image stored (no text detected)")
            
            logger.info(f"Processed image content for user {user_id}")
            
        except ContentProcessingError as e:
            logger.warning(f"Content processing error for user {user_id}: {e}")
            await processing_msg.edit_text(f"⚠️ {str(e)}")
        except Exception as e:
            logger.error(f"Error processing image for user {user_id}: {e}")
            await processing_msg.edit_text("❌ Failed to process image. Please try again later.")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document messages with enhanced error handling."""
        user_id = update.effective_user.id
        document = update.message.document
        
        # Send processing indicator
        processing_msg = await update.message.reply_text(f"🔄 Processing document: {document.file_name}...", quote=False)
        
        try:
            # Validate file size before processing
            if document.file_size > self.config.max_file_size_mb * 1024 * 1024:
                await processing_msg.edit_text(
                    f"❌ Document too large ({document.file_size / 1024 / 1024:.1f}MB). "
                    f"Maximum size: {self.config.max_file_size_mb}MB"
                )
                return
            
            # Get file
            file = await context.bot.get_file(document.file_id)
            
            # Process the document
            processed_content = await self.content_processor.process_document(file, document.file_name)
            
            # Classify the content if extraction was successful
            taxonomy = None
            if not processed_content.get('metadata', {}).get('error'):
                try:
                    taxonomy = await self.classifier.classify_content(processed_content['extracted_info'])
                except Exception as e:
                    logger.warning(f"Classification failed for user {user_id}: {e}")
                    taxonomy = {'error': str(e)}
            
            # Store in database with processing time
            processing_time = processed_content.get('metadata', {}).get('processing_time_ms')
            item_id = await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=f"Document: {document.file_name}",
                content_type="document",
                metadata=json.dumps(processed_content['metadata']),
                extracted_info=processed_content['extracted_info'],
                taxonomy=json.dumps(taxonomy) if taxonomy else None,
                processing_time_ms=processing_time
            )
            
            # Generate embedding for document content - disabled for now
            # if processed_content['extracted_info'] and processed_content['extracted_info'].strip():
            #     asyncio.create_task(
            #         self.embeddings_manager.store_embedding(
            #             item_id, processed_content['extracted_info']
            #         )
            #     )
            
            # Update processing message with result
            if processed_content.get('metadata', {}).get('error'):
                await processing_msg.edit_text(f"⚠️ Document stored with processing issues: {processed_content['metadata']['error'][:100]}")
            else:
                content_length = processed_content.get('metadata', {}).get('content_length', 0)
                await processing_msg.edit_text(f"✅ Document processed - extracted {content_length} characters")
            
            logger.info(f"Processed document content for user {user_id}")
            
        except ContentProcessingError as e:
            logger.warning(f"Content processing error for user {user_id}: {e}")
            await processing_msg.edit_text(f"⚠️ {str(e)}")
        except Exception as e:
            logger.error(f"Error processing document for user {user_id}: {e}")
            await processing_msg.edit_text("❌ Failed to process document. Please try again later.")
    
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