"""
Background parser service for RememBot.
Continuously processes pending content items with AI enhancement.
"""

import asyncio
import logging
import time
import signal
import sys
import json
from typing import Dict, Any, Optional
from pathlib import Path

# Use proper relative imports instead of sys.path.append
from .database import DatabaseManager
from .content_processor import ContentProcessor
from .classifier import ContentClassifier
from .config import get_config

logger = logging.getLogger(__name__)


class BackgroundParser:
    """Background service for processing content items."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize the background parser."""
        self.running = False
        self.db_manager = DatabaseManager(db_path or 'data/remembot.db')
        self.content_processor = ContentProcessor()
        self.classifier = ContentClassifier()
        
        try:
            self.config = get_config()
        except Exception as e:
            logger.warning(f"Could not load config, using defaults: {e}")
            from types import SimpleNamespace
            self.config = SimpleNamespace(
                parser_poll_interval=5,
                parser_batch_size=10,
                max_processing_time=300,
                parser_concurrency=3
            )
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    async def start(self):
        """Start the background parser service."""
        logger.info("Starting RememBot Background Parser")
        self.running = True
        
        # Initialize services (content processor doesn't need explicit initialization)
        logger.info("Background parser services initialized")
        
        # Main processing loop
        while self.running:
            try:
                await self._process_batch()
                await asyncio.sleep(getattr(self.config, 'parser_poll_interval', 5))
            except Exception as e:
                logger.error(f"Error in parser main loop: {e}", exc_info=True)
                await asyncio.sleep(10)  # Back off on errors
        
        # Cleanup
        await self.content_processor.close()
        logger.info("Background parser stopped")
    
    async def _process_batch(self):
        """Process a batch of pending items."""
        batch_size = getattr(self.config, 'parser_batch_size', 10)
        pending_items = await self.db_manager.get_pending_items(limit=batch_size)
        
        if not pending_items:
            return
        
        logger.info(f"Processing batch of {len(pending_items)} items")
        
        # Process items concurrently but with limited concurrency
        semaphore = asyncio.Semaphore(getattr(self.config, 'parser_concurrency', 3))  # Max concurrent processing
        tasks = [self._process_item_with_semaphore(item, semaphore) for item in pending_items]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _process_item_with_semaphore(self, item: Dict[str, Any], semaphore: asyncio.Semaphore):
        """Process a single item with semaphore protection."""
        async with semaphore:
            await self._process_item(item)
    
    async def _process_item(self, item: Dict[str, Any]):
        """Process a single content item."""
        item_id = item['id']
        content_type = item['content_type']
        original_share = item['original_share']
        
        start_time = time.time()
        
        try:
            # Mark as processing
            await self.db_manager.update_parse_status(item_id, 'processing')
            
            logger.info(f"Processing item {item_id} ({content_type}): {original_share[:100]}...")
            
            # Process based on content type
            if content_type == 'text':
                result = await self._process_text(original_share)
            elif content_type == 'url':
                result = await self._process_url(original_share)
            elif content_type == 'image':
                result = await self._process_image(item)
            elif content_type == 'document':
                result = await self._process_document(item)
            else:
                raise ValueError(f"Unknown content type: {content_type}")
            
            # Extract and classify content
            extracted_info = result.get('extracted_info', '')
            taxonomy = None
            
            if extracted_info and extracted_info.strip():
                try:
                    classification_result = await self.classifier.classify_content(extracted_info)
                    taxonomy = json.dumps(classification_result) if classification_result else None
                except Exception as e:
                    logger.warning(f"Classification failed for item {item_id}: {e}")
            
            # Calculate processing time
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Mark as complete
            await self.db_manager.update_parse_status(
                item_id, 
                'complete',
                extracted_info=extracted_info,
                taxonomy=taxonomy,
                processing_time_ms=processing_time_ms
            )
            
            logger.info(f"Successfully processed item {item_id} in {processing_time_ms:.1f}ms")
            
        except Exception as e:
            logger.error(f"Error processing item {item_id}: {e}", exc_info=True)
            await self.db_manager.update_parse_status(
                item_id, 
                'error',
                error_message=str(e)
            )
    
    async def _process_text(self, text: str) -> Dict[str, Any]:
        """Process plain text content."""
        # For plain text, we just return it as-is for classification
        return {
            'extracted_info': text,
            'metadata': {'content_length': len(text)}
        }
    
    async def _process_url(self, url: str) -> Dict[str, Any]:
        """Process URL content with enhanced fetching."""
        try:
            result = await self.content_processor.process_text(url)
            return result
        except Exception as e:
            # Fallback: try basic URL info
            logger.warning(f"Enhanced URL processing failed, using basic info: {e}")
            return {
                'extracted_info': f"URL: {url}",
                'metadata': {'url': url, 'error': str(e)}
            }
    
    async def _process_image(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Process image content with OCR and AI description."""
        # For background processing, we need to handle images that were already stored
        # This is a placeholder - in a real implementation, we'd need to store
        # the image file path or data for later processing
        return {
            'extracted_info': f"Image: {item['original_share']}",
            'metadata': {'type': 'image', 'note': 'Background image processing not yet implemented'}
        }
    
    async def _process_document(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Process document content with text extraction."""
        # Similar to images, this is a placeholder for background document processing
        return {
            'extracted_info': f"Document: {item['original_share']}",
            'metadata': {'type': 'document', 'note': 'Background document processing not yet implemented'}
        }
    
    async def get_status(self) -> Dict[str, Any]:
        """Get parser status and statistics."""
        parse_stats = await self.db_manager.get_parse_stats()
        
        return {
            'running': self.running,
            'parse_stats': parse_stats,
            'last_check': time.time()
        }


async def main():
    """Main entry point for the background parser service."""
    import os
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/background_parser.log') if os.path.exists('logs') else logging.NullHandler()
        ]
    )
    
    # Get database path from environment or use default
    db_path = os.environ.get('REMEMBOT_DATABASE_PATH', 'data/remembot.db')
    
    # Create and start parser
    parser = BackgroundParser(db_path)
    
    try:
        await parser.start()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error in background parser: {e}", exc_info=True)
        sys.exit(1)


def run_main():
    """Entry point for the background parser CLI."""
    import asyncio
    asyncio.run(main())


if __name__ == '__main__':
    run_main()