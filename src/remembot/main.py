#!/usr/bin/env python3
"""
RememBot - Remember Robot
Main entry point for the Telegram bot service.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from .bot import RememBot
from .database import DatabaseManager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for RememBot."""
    try:
        # Check for required environment variables
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN environment variable is required")
            sys.exit(1)
        
        # Set up database path
        db_path = os.getenv('REMEMBOT_DB_PATH', str(Path.home() / '.remembot' / 'remembot.db'))
        
        # Create database directory if it doesn't exist
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        db_manager = DatabaseManager(db_path)
        
        # Initialize and run bot
        bot = RememBot(bot_token, db_manager)
        
        logger.info("Starting RememBot...")
        asyncio.run(bot.run())
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()