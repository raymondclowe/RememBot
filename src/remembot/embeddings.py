"""
Embeddings system for RememBot. (sentence-transformers removed)
NOTE: All local semantic similarity and embedding features are disabled.
For future development, consider using OpenAI's embeddings API or another cloud-based service for semantic search and similarity.
"""

import asyncio
import logging
import numpy as np
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
import pickle
import os
from pathlib import Path
import time

SENTENCE_TRANSFORMERS_AVAILABLE = False  # sentence-transformers removed

from .config import get_config

logger = logging.getLogger(__name__)


class EmbeddingsManager:
    """Manages content embeddings for semantic search (DISABLED)."""
    
    def __init__(self, db_path: str):
        """Initialize embeddings manager."""
        self.db_path = db_path
        self.model = None
        self.model_name = "all-MiniLM-L6-v2"  # Placeholder name
        self.embedding_dim = 384  # Placeholder dimension
        self._model_lock = asyncio.Lock()
        
        try:
            self.config = get_config()
        except Exception:
            # Fallback for testing
            from types import SimpleNamespace
            self.config = SimpleNamespace()
        
        self._ensure_embeddings_table()
    
    def _ensure_embeddings_table(self):
        """Create embeddings table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            # Create embeddings table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS content_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_item_id INTEGER NOT NULL,
                    embedding BLOB NOT NULL,
                    model_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (content_item_id) REFERENCES content_items (id),
                    UNIQUE(content_item_id, model_name)
                )
            ''')
            
            # Create index for fast lookups
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_embeddings_content_id 
                ON content_embeddings(content_item_id)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_embeddings_model 
                ON content_embeddings(model_name)
            ''')
            
            conn.commit()
            logger.info("Embeddings table initialized")
    
    async def _get_model(self):
        """
        Stub: sentence-transformers is not available. For future semantic similarity, use a cloud API.
        """
        logger.warning("sentence-transformers not available (stubbed)")
        return None
    
    async def generate_embedding(self, text: str):
        """
        Stub: Embedding generation is disabled. For future, use OpenAI embeddings API or similar.
        """
        logger.warning("Embedding generation is disabled (sentence-transformers removed)")
        return None
    
    async def store_embedding(
        self, 
        content_item_id: int, 
        text: str,
        force_update: bool = False
    ) -> bool:
        """Store embedding for content item."""
        if not text or not text.strip():
            return False
        
        # Stub: Embedding generation is disabled
        return False
    
    async def semantic_search(
        self, 
        user_telegram_id: int,
        query: str,
        limit: int = 10,
        similarity_threshold: float = 0.3
    ):
        """
        Stub: Semantic search is disabled. For future, use OpenAI embeddings API or similar.
        """
        logger.warning("Semantic search not available (sentence-transformers removed)")
        return []
    
    async def batch_generate_embeddings(
        self, 
        user_telegram_id: Optional[int] = None,
        batch_size: int = 50
    ):
        """
        Stub: Batch embedding generation is disabled. For future, use OpenAI embeddings API or similar.
        """
        logger.warning("Batch embedding generation is disabled (sentence-transformers removed)")
        return {'processed': 0, 'errors': 0, 'skipped': 0}
    
    async def get_similar_content(
        self, 
        content_item_id: int,
        user_telegram_id: int,
        limit: int = 5
    ):
        """
        Stub: Similar content search is disabled. For future, use OpenAI embeddings API or similar.
        """
        logger.warning("Similar content search is disabled (sentence-transformers removed)")
        return []
    
    async def get_embedding_stats(self) -> Dict[str, Any]:
        """Get statistics about embeddings."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Total embeddings
                cursor = conn.execute('SELECT COUNT(*) FROM content_embeddings')
                total_embeddings = cursor.fetchone()[0]
                
                # Embeddings by model
                cursor = conn.execute('''
                    SELECT model_name, COUNT(*) 
                    FROM content_embeddings 
                    GROUP BY model_name
                ''')
                by_model = dict(cursor.fetchall())
                
                # Coverage (items with embeddings vs total items)
                cursor = conn.execute('SELECT COUNT(*) FROM content_items')
                total_items = cursor.fetchone()[0]
                
                coverage_percent = (total_embeddings / total_items * 100) if total_items > 0 else 0
                
                return {
                    'total_embeddings': total_embeddings,
                    'total_content_items': total_items,
                    'coverage_percent': round(coverage_percent, 1),
                    'by_model': by_model,
                    'model_available': SENTENCE_TRANSFORMERS_AVAILABLE,
                    'current_model': self.model_name
                }
        
        except Exception as e:
            logger.error(f"Error getting embedding stats: {e}")
            return {
                'error': str(e),
                'model_available': SENTENCE_TRANSFORMERS_AVAILABLE
            }