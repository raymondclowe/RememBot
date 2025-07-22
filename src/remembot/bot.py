"""
Telegram bot implementation for RememBot.
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

from .database import DatabaseManager
from .content_processor import ContentProcessor
from .classifier import ContentClassifier
from .query_handler import QueryHandler

logger = logging.getLogger(__name__)


class RememBot:
    """Main Telegram bot class."""
    
    def __init__(self, token: str, db_manager: DatabaseManager):
        """Initialize RememBot."""
        self.token = token
        self.db_manager = db_manager
        self.content_processor = ContentProcessor()
        self.classifier = ContentClassifier()
        self.query_handler = QueryHandler(db_manager)
        
        # Create application
        self.application = Application.builder().token(token).build()
        
        # Add handlers
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up message and command handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("search", self.search_command))
        
        # Message handlers for content ingestion
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        welcome_message = (
            f"Welcome to RememBot, {user.first_name}! 🤖\n\n"
            "I'm your personal knowledge assistant. Share any content with me:\n"
            "• URLs - I'll extract and store the content\n"
            "• Images - I'll analyze and extract text (OCR)\n"
            "• Documents - I'll parse and index them\n"
            "• Text - I'll store and classify it\n\n"
            "Later, use /search <query> to find what you've shared.\n"
            "Use /help for more commands."
        )
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "RememBot Commands:\n\n"
            "/start - Welcome message\n"
            "/help - Show this help\n"
            "/stats - Show your storage statistics\n"
            "/search <query> - Search your stored content\n\n"
            "Just share any content with me and I'll store it silently for later retrieval!"
        )
        await update.message.reply_text(help_text)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command."""
        user_id = update.effective_user.id
        stats = await self.db_manager.get_user_stats(user_id)
        
        stats_text = (
            f"📊 Your RememBot Statistics:\n\n"
            f"Total items stored: {stats['total_items']}\n"
            f"Recent items (7 days): {stats['recent_items']}\n\n"
            "Items by type:\n"
        )
        
        for content_type, count in stats['items_by_type'].items():
            stats_text += f"• {content_type}: {count}\n"
        
        await update.message.reply_text(stats_text)
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command."""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text("Please provide a search query. Example: /search python tutorial")
            return
        
        query = " ".join(context.args)
        results = await self.query_handler.process_query(user_id, query)
        
        if not results:
            await update.message.reply_text(f"No results found for '{query}'. Try a different search term.")
            return
        
        # Format results
        response = f"🔍 Found {len(results)} result(s) for '{query}':\n\n"
        
        for i, item in enumerate(results[:5], 1):  # Limit to first 5 results
            content_preview = (item['extracted_info'] or item['original_share'])[:100]
            if len(content_preview) == 100:
                content_preview += "..."
            
            response += (
                f"{i}. [{item['content_type']}] {content_preview}\n"
                f"   📅 {item['created_at']}\n\n"
            )
        
        await update.message.reply_text(response)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (URLs and plain text)."""
        user_id = update.effective_user.id
        text = update.message.text
        
        try:
            # Process the content
            processed_content = await self.content_processor.process_text(text)
            
            # Classify the content
            taxonomy = await self.classifier.classify_content(processed_content['extracted_info'])
            
            # Store in database
            await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=text,
                content_type=processed_content['content_type'],
                metadata=json.dumps(processed_content['metadata']),
                extracted_info=processed_content['extracted_info'],
                taxonomy=json.dumps(taxonomy)
            )
            
            logger.info(f"Processed text content for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error processing text for user {user_id}: {e}")
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages."""
        user_id = update.effective_user.id
        photo = update.message.photo[-1]  # Get highest resolution
        
        try:
            # Get file
            file = await context.bot.get_file(photo.file_id)
            
            # Process the image
            processed_content = await self.content_processor.process_image(file)
            
            # Classify the content
            taxonomy = await self.classifier.classify_content(processed_content['extracted_info'])
            
            # Store in database
            await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=f"Photo: {photo.file_id}",
                content_type="image",
                metadata=json.dumps(processed_content['metadata']),
                extracted_info=processed_content['extracted_info'],
                taxonomy=json.dumps(taxonomy)
            )
            
            logger.info(f"Processed image content for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error processing image for user {user_id}: {e}")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document messages."""
        user_id = update.effective_user.id
        document = update.message.document
        
        try:
            # Get file
            file = await context.bot.get_file(document.file_id)
            
            # Process the document
            processed_content = await self.content_processor.process_document(file, document.file_name)
            
            # Classify the content
            taxonomy = await self.classifier.classify_content(processed_content['extracted_info'])
            
            # Store in database
            await self.db_manager.store_content(
                user_telegram_id=user_id,
                original_share=f"Document: {document.file_name}",
                content_type="document",
                metadata=json.dumps(processed_content['metadata']),
                extracted_info=processed_content['extracted_info'],
                taxonomy=json.dumps(taxonomy)
            )
            
            logger.info(f"Processed document content for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error processing document for user {user_id}: {e}")
    
    async def run(self):
        """Run the bot using long polling."""
        logger.info("Starting RememBot with long polling...")
        
        # Start polling
        await self.application.run_polling(
            poll_interval=1.0,
            timeout=10,
            bootstrap_retries=5,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )