"""
Configuration management for RememBot.
Provides environment-based configuration with validation.
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class RememBotConfig(BaseSettings):
    """RememBot configuration with validation."""
    
    # Required settings
    telegram_bot_token: str = Field(..., description="Telegram bot token from BotFather")
    
    # Optional AI settings
    openrouter_api_key: Optional[str] = Field(None, description="OpenRouter API key for AI features")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key for AI features (fallback)")
    
    # Database settings
    database_path: str = Field(
        default_factory=lambda: str(Path.home() / '.remembot' / 'remembot.db'),
        description="Path to SQLite database file"
    )
    
    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        description="Log format string"
    )
    
    # Performance settings
    max_workers: int = Field(default=4, description="Maximum worker threads for content processing")
    request_timeout: int = Field(default=30, description="HTTP request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retries for failed operations")
    
    # Content processing settings
    max_file_size_mb: int = Field(default=50, description="Maximum file size in MB")
    supported_image_formats: list = Field(
        default=['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff'],
        description="Supported image formats"
    )
    supported_document_formats: list = Field(
        default=['pdf', 'docx', 'xlsx', 'txt'],
        description="Supported document formats"
    )
    
    # Health check settings
    health_check_enabled: bool = Field(default=True, description="Enable health check endpoint")
    health_check_port: int = Field(default=8080, description="Health check endpoint port")
    
    @field_validator('telegram_bot_token')
    @classmethod
    def validate_telegram_token(cls, v):
        """Validate Telegram bot token format."""
        if not v:
            raise ValueError("Telegram bot token is required")
        if ':' not in v or len(v.split(':')) != 2:
            raise ValueError("Invalid Telegram bot token format")
        return v
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    @field_validator('database_path')
    @classmethod
    def validate_database_path(cls, v):
        """Ensure database directory exists."""
        db_path = Path(v)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return str(db_path)
    
    @field_validator('max_file_size_mb')
    @classmethod
    def validate_file_size(cls, v):
        """Validate file size limit."""
        if v <= 0 or v > 100:
            raise ValueError("File size must be between 1 and 100 MB")
        return v
    
    model_config = {
        "env_file": ".env",
        "env_prefix": "REMEMBOT_",
        "case_sensitive": False
    }


class ConfigManager:
    """Manages RememBot configuration with hot-reloading."""
    
    def __init__(self):
        """Initialize configuration manager."""
        self._config: Optional[RememBotConfig] = None
        self._config_file_mtime: Optional[float] = None
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up basic logging before config is loaded."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def load_config(self, force_reload: bool = False) -> RememBotConfig:
        """Load configuration with optional hot-reloading."""
        config_file = Path('.env')
        
        # Check if we need to reload
        should_reload = force_reload or self._config is None
        
        if config_file.exists():
            current_mtime = config_file.stat().st_mtime
            if self._config_file_mtime != current_mtime:
                should_reload = True
                self._config_file_mtime = current_mtime
        
        if should_reload:
            try:
                self._config = RememBotConfig()
                self._configure_logging()
                logger.info("Configuration loaded successfully")
                self._log_config_summary()
            except ValidationError as e:
                logger.error(f"Configuration validation error: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to load configuration: {e}")
                raise
        
        return self._config
    
    def _configure_logging(self):
        """Configure logging based on config settings."""
        if not self._config:
            return
        
        # Update log level
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self._config.log_level))
        
        # Update formatter
        for handler in root_logger.handlers:
            handler.setFormatter(logging.Formatter(self._config.log_format))
    
    def _log_config_summary(self):
        """Log configuration summary (without sensitive data)."""
        if not self._config:
            return
        
        logger.info("Configuration Summary:")
        logger.info(f"  Database: {self._config.database_path}")
        logger.info(f"  Log Level: {self._config.log_level}")
        logger.info(f"  Max Workers: {self._config.max_workers}")
        logger.info(f"  Request Timeout: {self._config.request_timeout}s")
        logger.info(f"  Max File Size: {self._config.max_file_size_mb}MB")
        logger.info(f"  AI Features: {'Enabled' if self.has_ai_api_key() else 'Disabled'}")
        logger.info(f"  Health Check: {'Enabled' if self._config.health_check_enabled else 'Disabled'}")
    
    def has_ai_api_key(self) -> bool:
        """Check if any AI API key is configured."""
        if not self._config:
            return False
        return bool(self._config.openrouter_api_key or self._config.openai_api_key)
    
    def get_ai_api_key(self) -> Optional[str]:
        """Get the first available AI API key (prioritizing OpenRouter)."""
        if not self._config:
            return None
        return self._config.openrouter_api_key or self._config.openai_api_key
    
    def validate_startup_requirements(self):
        """Validate that all required configuration is present."""
        if not self._config:
            raise RuntimeError("Configuration not loaded")
        
        errors = []
        
        # Check Telegram token
        if not self._config.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        
        # Check database path is writable
        try:
            db_path = Path(self._config.database_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            test_file = db_path.parent / '.write_test'
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            errors.append(f"Database path not writable: {e}")
        
        if errors:
            error_msg = "Startup validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info("✓ Startup validation passed")
    
    @property
    def config(self) -> RememBotConfig:
        """Get current configuration."""
        if not self._config:
            return self.load_config()
        return self._config


# Global configuration manager instance
config_manager = ConfigManager()


def get_config() -> RememBotConfig:
    """Get the global configuration instance."""
    return config_manager.load_config()


def reload_config() -> RememBotConfig:
    """Force reload of configuration."""
    return config_manager.load_config(force_reload=True)