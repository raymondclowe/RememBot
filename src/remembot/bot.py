"""
Telegram bot implementation for RememBot with enhanced error handling.
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
    """Main Telegram bot class with enhanced error handling."""
    
    def __init__(self, token: str, db_manager: DatabaseManager):
        """Initialize RememBot."""
        self.token = token
        self.db_manager = db_manager
        self.config = get_config()
        self.content_processor = ContentProcessor()
        self.classifier = ContentClassifier()
        self.query_handler = QueryHandler(db_manager)
        self.health_checker = HealthChecker(db_manager)
        self.embeddings_manager = EmbeddingsManager(config.database_path)
        
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
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("search", self.search_command))
        self.application.add_handler(CommandHandler("semantic", self.semantic_search_command))
        self.application.add_handler(CommandHandler("similar", self.similar_command))
        self.application.add_handler(CommandHandler("embeddings", self.embeddings_command))
        
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
            "/search <query> - Search your stored content\n"
            "/semantic <query> - Semantic search (AI-powered)\n"
            "/similar <content_id> - Find similar content\n"
            "/embeddings - Show AI embedding statistics\n\n"
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
        """Handle /search command with enhanced FTS5 support."""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "Please provide a search query. Example: /search python tutorial\n\n"
                "Advanced options:\n"
                "• /search type:url python - Search only URLs\n"
                "• /search platform:youtube - Search specific platforms\n"
                "• /search \"exact phrase\" - Exact phrase search"
            )
            return
        
        query = " ".join(context.args)
        
        # Parse search modifiers
        content_type = None
        source_platform = None
        
        # Extract type filter
        if "type:" in query:
            parts = query.split("type:")
            if len(parts) > 1:
                type_part = parts[1].split()[0]
                content_type = type_part
                query = query.replace(f"type:{type_part}", "").strip()
        
        # Extract platform filter
        if "platform:" in query:
            parts = query.split("platform:")
            if len(parts) > 1:
                platform_part = parts[1].split()[0]
                source_platform = platform_part
                query = query.replace(f"platform:{platform_part}", "").strip()
        
        if not query.strip():
            await update.message.reply_text("Please provide a search term after filters.")
            return
        
        try:
            # Search with enhanced database
            results, total = await self.db_manager.search_content(
                user_id, query, content_type=content_type, 
                source_platform=source_platform, limit=10
            )
            
            if not results:
                await update.message.reply_text(
                    f"No results found for '{query}'. Try:\n"
                    "• Different keywords\n"
                    "• Removing filters\n"
                    "• Checking spelling"
                )
                return
            
            # Format results with enhanced information
            response = f"🔍 Found {len(results)} of {total} result(s) for '{query}'"
            if content_type:
                response += f" (type: {content_type})"
            if source_platform:
                response += f" (platform: {source_platform})"
            response += ":\n\n"
            
            for i, item in enumerate(results[:5], 1):  # Limit to first 5 results
                content_preview = (item['extracted_info'] or item['original_share'])[:100]
                if len(content_preview) == 100:
                    content_preview += "..."
                
                # Add platform info if available
                platform_info = ""
                if item.get('source_platform'):
                    platform_info = f" [{item['source_platform']}]"
                
                response += (
                    f"{i}. [{item['content_type']}{platform_info}] {content_preview}\n"
                    f"   📅 {item['created_at']}\n\n"
                )
            
            if total > 5:
                response += f"\n... and {total - 5} more results. Use more specific terms to narrow down."
            
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Search error for user {user_id}: {e}")
            await update.message.reply_text("❌ Search failed. Please try again later.")
    
    async def semantic_search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /semantic command for AI-powered semantic search."""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "Please provide a search query for semantic search.\n"
                "Example: /semantic machine learning concepts\n\n"
                "Semantic search understands meaning and context, not just keywords."
            )
            return
        
        query = " ".join(context.args)
        
        # Send processing indicator
        processing_msg = await update.message.reply_text("🧠 Performing AI semantic search...", quote=False)
        
        try:
            # Perform semantic search
            results = await self.embeddings_manager.semantic_search(
                user_id, query, limit=10, similarity_threshold=0.3
            )
            
            if not results:
                await processing_msg.edit_text(
                    f"🤖 No semantically similar results found for '{query}'.\n\n"
                    "Tips:\n"
                    "• Try broader or different terms\n"
                    "• Use /search for keyword-based search\n"
                    "• More content helps improve AI search"
                )
                return
            
            # Format results with similarity scores
            response = f"🧠 Found {len(results)} semantically similar result(s) for '{query}':\n\n"
            
            for i, item in enumerate(results[:5], 1):
                content_preview = (item['extracted_info'] or item['original_share'])[:100]
                if len(content_preview) == 100:
                    content_preview += "..."
                
                # Add platform info if available
                platform_info = ""
                if item.get('source_platform'):
                    platform_info = f" [{item['source_platform']}]"
                
                # Format similarity score
                similarity = item['similarity_score']
                similarity_bar = "🟢" if similarity > 0.7 else "🟡" if similarity > 0.5 else "🟠"
                
                response += (
                    f"{i}. {similarity_bar} {similarity:.1%} similarity\n"
                    f"[{item['content_type']}{platform_info}] {content_preview}\n"
                    f"📅 {item['created_at']}\n\n"
                )
            
            if len(results) > 5:
                response += f"... and {len(results) - 5} more results."
            
            await processing_msg.edit_text(response)
            
        except Exception as e:
            logger.error(f"Semantic search error for user {user_id}: {e}")
            await processing_msg.edit_text("❌ Semantic search failed. Please try again later.")
    
    async def similar_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /similar command to find content similar to a specific item."""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "Please provide a content ID to find similar items.\n"
                "Example: /similar 123\n\n"
                "You can get content IDs from search results."
            )
            return
        
        try:
            content_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Please provide a valid content ID (number).")
            return
        
        try:
            # Find similar content
            results = await self.embeddings_manager.get_similar_content(
                content_id, user_id, limit=5
            )
            
            if not results:
                await update.message.reply_text(
                    f"No similar content found for item {content_id}.\n"
                    "This might mean:\n"
                    "• The content doesn't exist or isn't yours\n"
                    "• No AI embeddings are available for comparison\n"
                    "• No other content is similar enough"
                )
                return
            
            # Format results
            response = f"🔗 Content similar to item {content_id}:\n\n"
            
            for i, item in enumerate(results, 1):
                content_preview = (item['extracted_info'] or item['original_share'])[:80]
                if len(content_preview) == 80:
                    content_preview += "..."
                
                similarity = item['similarity_score']
                similarity_bar = "🟢" if similarity > 0.7 else "🟡" if similarity > 0.5 else "🟠"
                
                response += (
                    f"{i}. {similarity_bar} {similarity:.1%} similarity\n"
                    f"ID: {item['id']} | {content_preview}\n"
                    f"📅 {item['created_at']}\n\n"
                )
            
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Similar content error for user {user_id}: {e}")
            await update.message.reply_text("❌ Failed to find similar content. Please try again later.")
    
    async def embeddings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /embeddings command to show AI embedding statistics."""
        user_id = update.effective_user.id
        
        try:
            # Get embedding statistics
            stats = await self.embeddings_manager.get_embedding_stats()
            
            if 'error' in stats:
                await update.message.reply_text(f"❌ Error getting embedding stats: {stats['error']}")
                return
            
            response = "🧠 AI Embedding Statistics:\n\n"
            
            if not stats['model_available']:
                response += "❌ AI embeddings not available (sentence-transformers not installed)\n"
            else:
                response += f"✅ AI Model: {stats['current_model']}\n"
                response += f"📊 Total embeddings: {stats['total_embeddings']:,}\n"
                response += f"📋 Total content items: {stats['total_content_items']:,}\n"
                response += f"📈 Coverage: {stats['coverage_percent']}%\n\n"
                
                if stats['coverage_percent'] < 100:
                    missing = stats['total_content_items'] - stats['total_embeddings']
                    response += f"⚠️ {missing:,} items need embeddings generated\n"
                    response += "Use /semantic search to automatically generate embeddings\n\n"
                
                response += "Models:\n"
                for model, count in stats['by_model'].items():
                    response += f"• {model}: {count:,} embeddings\n"
            
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Embeddings stats error for user {user_id}: {e}")
            await update.message.reply_text("❌ Failed to get embedding statistics.")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (URLs and plain text) with enhanced error handling."""
        user_id = update.effective_user.id
        text = update.message.text
        
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
            
            # Generate embedding asynchronously (don't wait for completion)
            if processed_content['extracted_info'] and processed_content['extracted_info'].strip():
                asyncio.create_task(
                    self.embeddings_manager.store_embedding(
                        item_id, processed_content['extracted_info']
                    )
                )
            
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
            
            # Generate embedding for OCR text if available
            if (processed_content.get('metadata', {}).get('has_text') and 
                processed_content['extracted_info'] and 
                processed_content['extracted_info'].strip()):
                asyncio.create_task(
                    self.embeddings_manager.store_embedding(
                        item_id, processed_content['extracted_info']
                    )
                )
            
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
            
            # Generate embedding for document content
            if processed_content['extracted_info'] and processed_content['extracted_info'].strip():
                asyncio.create_task(
                    self.embeddings_manager.store_embedding(
                        item_id, processed_content['extracted_info']
                    )
                )
            
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
    
    async def startup(self):
        """Initialize services on startup."""
        try:
            await self.health_checker.start()
            logger.info("Health checker started")
        except Exception as e:
            logger.warning(f"Failed to start health checker: {e}")
    
    async def shutdown(self):
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
            bootstrap_retries=self.config.max_retries,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30
        )