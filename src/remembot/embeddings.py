"""
Embeddings system for RememBot using sentence-transformers.
Provides semantic search capabilities with vector similarity.
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

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

from .config import get_config

logger = logging.getLogger(__name__)


class EmbeddingsManager:
    """Manages content embeddings for semantic search."""
    
    def __init__(self, db_path: str):
        """Initialize embeddings manager."""
        self.db_path = db_path
        self.model = None
        self.model_name = "all-MiniLM-L6-v2"  # Lightweight, fast model
        self.embedding_dim = 384  # Dimension for all-MiniLM-L6-v2
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
    
    async def _get_model(self) -> Optional[SentenceTransformer]:
        """Get or load the sentence transformer model."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers not available")
            return None
        
        async with self._model_lock:
            if self.model is None:
                try:
                    logger.info(f"Loading sentence transformer model: {self.model_name}")
                    # Run model loading in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    self.model = await loop.run_in_executor(
                        None, SentenceTransformer, self.model_name
                    )
                    logger.info(f"Model loaded successfully (dimension: {self.embedding_dim})")
                except Exception as e:
                    logger.error(f"Failed to load sentence transformer model: {e}")
                    return None
            
            return self.model
    
    async def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text."""
        if not text or not text.strip():
            return None
        
        model = await self._get_model()
        if model is None:
            return None
        
        try:
            # Run embedding generation in thread pool
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None, model.encode, text.strip()
            )
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
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
        
        # Check if embedding already exists
        with sqlite3.connect(self.db_path) as conn:
            if not force_update:
                cursor = conn.execute('''
                    SELECT id FROM content_embeddings 
                    WHERE content_item_id = ? AND model_name = ?
                ''', (content_item_id, self.model_name))
                
                if cursor.fetchone():
                    logger.debug(f"Embedding already exists for content {content_item_id}")
                    return True
        
        # Generate embedding
        embedding = await self.generate_embedding(text)
        if embedding is None:
            return False
        
        # Store embedding
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Serialize embedding as blob
                embedding_blob = pickle.dumps(embedding)
                
                conn.execute('''
                    INSERT OR REPLACE INTO content_embeddings 
                    (content_item_id, embedding, model_name)
                    VALUES (?, ?, ?)
                ''', (content_item_id, embedding_blob, self.model_name))
                
                conn.commit()
                logger.debug(f"Stored embedding for content {content_item_id}")
                return True
        except Exception as e:
            logger.error(f"Error storing embedding for content {content_item_id}: {e}")
            return False
    
    async def semantic_search(
        self, 
        user_telegram_id: int,
        query: str,
        limit: int = 10,
        similarity_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Perform semantic search using embeddings."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("Semantic search not available - sentence-transformers not installed")
            return []
        
        start_time = time.time()
        
        # Generate query embedding
        query_embedding = await self.generate_embedding(query)
        if query_embedding is None:
            logger.warning("Could not generate query embedding")
            return []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Get all embeddings for user's content
                cursor = conn.execute('''
                    SELECT ce.content_item_id, ce.embedding, ci.original_share, 
                           ci.content_type, ci.extracted_info, ci.created_at,
                           ci.source_platform
                    FROM content_embeddings ce
                    JOIN content_items ci ON ce.content_item_id = ci.id
                    WHERE ci.user_telegram_id = ? AND ce.model_name = ?
                    ORDER BY ci.created_at DESC
                ''', (user_telegram_id, self.model_name))
                
                results = []
                
                for row in cursor:
                    try:
                        content_id, embedding_blob, original_share, content_type, extracted_info, created_at, source_platform = row
                        
                        # Deserialize embedding
                        content_embedding = pickle.loads(embedding_blob)
                        
                        # Calculate cosine similarity
                        similarity = self._cosine_similarity(query_embedding, content_embedding)
                        
                        if similarity >= similarity_threshold:
                            results.append({
                                'id': content_id,
                                'original_share': original_share,
                                'content_type': content_type,
                                'extracted_info': extracted_info,
                                'created_at': created_at,
                                'source_platform': source_platform,
                                'similarity_score': similarity
                            })
                    
                    except Exception as e:
                        logger.warning(f"Error processing embedding for content {content_id}: {e}")
                        continue
                
                # Sort by similarity score (descending)
                results.sort(key=lambda x: x['similarity_score'], reverse=True)
                
                search_time = (time.time() - start_time) * 1000
                logger.info(f"Semantic search found {len(results)} results in {search_time:.1f}ms")
                
                return results[:limit]
        
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            # Normalize vectors
            a_norm = a / np.linalg.norm(a)
            b_norm = b / np.linalg.norm(b)
            
            # Calculate cosine similarity
            similarity = np.dot(a_norm, b_norm)
            
            # Ensure it's a float (sometimes numpy returns array)
            return float(similarity)
        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {e}")
            return 0.0
    
    async def batch_generate_embeddings(
        self, 
        user_telegram_id: Optional[int] = None,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """Generate embeddings for content that doesn't have them."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("Cannot generate embeddings - sentence-transformers not available")
            return {'processed': 0, 'errors': 0, 'skipped': 0}
        
        logger.info(f"Starting batch embedding generation (batch_size: {batch_size})")
        
        stats = {'processed': 0, 'errors': 0, 'skipped': 0}
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Find content without embeddings
                if user_telegram_id:
                    cursor = conn.execute('''
                        SELECT ci.id, ci.extracted_info, ci.original_share
                        FROM content_items ci
                        LEFT JOIN content_embeddings ce ON ci.id = ce.content_item_id 
                            AND ce.model_name = ?
                        WHERE ci.user_telegram_id = ? AND ce.id IS NULL
                        ORDER BY ci.created_at DESC
                    ''', (self.model_name, user_telegram_id))
                else:
                    cursor = conn.execute('''
                        SELECT ci.id, ci.extracted_info, ci.original_share
                        FROM content_items ci
                        LEFT JOIN content_embeddings ce ON ci.id = ce.content_item_id 
                            AND ce.model_name = ?
                        WHERE ce.id IS NULL
                        ORDER BY ci.created_at DESC
                    ''', (self.model_name,))
                
                items = cursor.fetchall()
                logger.info(f"Found {len(items)} items without embeddings")
                
                # Process in batches
                for i in range(0, len(items), batch_size):
                    batch = items[i:i + batch_size]
                    
                    for content_id, extracted_info, original_share in batch:
                        try:
                            # Use extracted_info if available, otherwise original_share
                            text = extracted_info if extracted_info and extracted_info.strip() else original_share
                            
                            if not text or not text.strip():
                                stats['skipped'] += 1
                                continue
                            
                            success = await self.store_embedding(content_id, text)
                            if success:
                                stats['processed'] += 1
                            else:
                                stats['errors'] += 1
                        
                        except Exception as e:
                            logger.error(f"Error processing content {content_id}: {e}")
                            stats['errors'] += 1
                    
                    # Small delay between batches
                    if i + batch_size < len(items):
                        await asyncio.sleep(0.1)
                
                logger.info(f"Batch embedding generation complete: {stats}")
                return stats
        
        except Exception as e:
            logger.error(f"Error in batch embedding generation: {e}")
            return stats
    
    async def get_similar_content(
        self, 
        content_item_id: int,
        user_telegram_id: int,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Find content similar to a specific item."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Get the embedding for the reference content
                cursor = conn.execute('''
                    SELECT embedding FROM content_embeddings 
                    WHERE content_item_id = ? AND model_name = ?
                ''', (content_item_id, self.model_name))
                
                result = cursor.fetchone()
                if not result:
                    logger.warning(f"No embedding found for content {content_item_id}")
                    return []
                
                reference_embedding = pickle.loads(result[0])
                
                # Get all other embeddings for this user
                cursor = conn.execute('''
                    SELECT ce.content_item_id, ce.embedding, ci.original_share, 
                           ci.content_type, ci.extracted_info, ci.created_at,
                           ci.source_platform
                    FROM content_embeddings ce
                    JOIN content_items ci ON ce.content_item_id = ci.id
                    WHERE ci.user_telegram_id = ? AND ce.model_name = ? 
                    AND ce.content_item_id != ?
                    ORDER BY ci.created_at DESC
                ''', (user_telegram_id, self.model_name, content_item_id))
                
                similarities = []
                
                for row in cursor:
                    try:
                        content_id, embedding_blob, original_share, content_type, extracted_info, created_at, source_platform = row
                        
                        content_embedding = pickle.loads(embedding_blob)
                        similarity = self._cosine_similarity(reference_embedding, content_embedding)
                        
                        similarities.append({
                            'id': content_id,
                            'original_share': original_share,
                            'content_type': content_type,
                            'extracted_info': extracted_info,
                            'created_at': created_at,
                            'source_platform': source_platform,
                            'similarity_score': similarity
                        })
                    
                    except Exception as e:
                        logger.warning(f"Error processing similarity for content {content_id}: {e}")
                        continue
                
                # Sort by similarity and return top results
                similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
                return similarities[:limit]
        
        except Exception as e:
            logger.error(f"Error finding similar content: {e}")
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