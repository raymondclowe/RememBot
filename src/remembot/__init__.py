"""
RememBot - Remember Robot
A Telegram bot that backs up your brain by storing and organizing shared content.
"""

__version__ = "0.1.0"
__author__ = "Raymond Lowe"
__description__ = "RememBot - Remember Robot, a Telegram bot that backs up your brain"

from .main import main
from .bot import RememBot
from .database import DatabaseManager
from .content_processor import ContentProcessor
from .classifier import ContentClassifier
from .query_handler import QueryHandler

__all__ = [
    "main",
    "RememBot", 
    "DatabaseManager",
    "ContentProcessor",
    "ContentClassifier", 
    "QueryHandler"
]
