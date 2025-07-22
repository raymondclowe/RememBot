#!/usr/bin/env python3
"""
RememBot - Remember Robot
Main entry point for the Telegram bot service with enhanced configuration and error handling.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from .bot import RememBot
from .database import DatabaseManager
from .config import config_manager


def main():
    """Main entry point for RememBot with enhanced configuration."""
    try:
        # Load and validate configuration
        config = config_manager.load_config()
        config_manager.validate_startup_requirements()
        
        # Initialize database
        db_manager = DatabaseManager(config.database_path)
        
        # Initialize and run bot
        bot = RememBot(config.telegram_bot_token, db_manager)
        
        logger = logging.getLogger(__name__)
        logger.info("🤖 RememBot starting...")
        logger.info(f"📊 Database: {config.database_path}")
        logger.info(f"🔧 Configuration loaded successfully")
        
        bot.run()
        
    except KeyboardInterrupt:
        logger = logging.getLogger(__name__)
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"💥 Fatal error: {e}")
        
        # Print configuration guidance
        if "TELEGRAM_BOT_TOKEN" in str(e):
            print("\n❌ Configuration Error:")
            print("Please set your Telegram bot token:")
            print("  export TELEGRAM_BOT_TOKEN=your_bot_token_here")
            print("  or create a .env file with: TELEGRAM_BOT_TOKEN=your_bot_token_here")
            print("\nGet a token from @BotFather on Telegram")
        
        sys.exit(1)


if __name__ == "__main__":
    main()