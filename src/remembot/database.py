"""
Database manager for RememBot.
Handles SQLite operations and schema management.
"""

import sqlite3
import aiosqlite
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database operations for RememBot."""
    
    def __init__(self, db_path: str):
        """Initialize database manager."""
        self.db_path = db_path
        self._ensure_database_exists()
    
    def _ensure_database_exists(self):
        """Create database and tables if they don't exist."""
        # Create database directory if it doesn't exist
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Create tables using synchronous connection for initialization
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS content_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_telegram_id INTEGER NOT NULL,
                    original_share TEXT NOT NULL,
                    metadata TEXT,
                    extracted_info TEXT,
                    taxonomy TEXT,
                    content_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_telegram_id 
                ON content_items(user_telegram_id)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_content_type 
                ON content_items(content_type)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON content_items(created_at)
            ''')
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
    
    async def store_content(
        self, 
        user_telegram_id: int,
        original_share: str,
        content_type: str,
        metadata: Optional[str] = None,
        extracted_info: Optional[str] = None,
        taxonomy: Optional[str] = None
    ) -> int:
        """Store a content item in the database."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO content_items 
                (user_telegram_id, original_share, content_type, metadata, extracted_info, taxonomy)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_telegram_id, original_share, content_type, metadata, extracted_info, taxonomy))
            
            await db.commit()
            item_id = cursor.lastrowid
            logger.info(f"Stored content item {item_id} for user {user_telegram_id}")
            return item_id
    
    async def search_content(
        self, 
        user_telegram_id: int, 
        query: str,
        content_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for content items."""
        async with aiosqlite.connect(self.db_path) as db:
            # Simple text search in extracted_info and original_share
            # TODO: Implement more sophisticated search with AI
            search_term = f"%{query}%"
            
            if content_type:
                cursor = await db.execute('''
                    SELECT id, original_share, content_type, metadata, extracted_info, 
                           taxonomy, created_at 
                    FROM content_items 
                    WHERE user_telegram_id = ? 
                    AND content_type = ?
                    AND (extracted_info LIKE ? OR original_share LIKE ?)
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (user_telegram_id, content_type, search_term, search_term, limit))
            else:
                cursor = await db.execute('''
                    SELECT id, original_share, content_type, metadata, extracted_info, 
                           taxonomy, created_at 
                    FROM content_items 
                    WHERE user_telegram_id = ? 
                    AND (extracted_info LIKE ? OR original_share LIKE ?)
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (user_telegram_id, search_term, search_term, limit))
            
            rows = await cursor.fetchall()
            
            # Convert rows to dictionaries
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in rows]
            
            logger.info(f"Found {len(results)} items for query '{query}' by user {user_telegram_id}")
            return results
    
    async def get_user_stats(self, user_telegram_id: int) -> Dict[str, Any]:
        """Get statistics for a user's stored content."""
        async with aiosqlite.connect(self.db_path) as db:
            # Total items
            cursor = await db.execute('''
                SELECT COUNT(*) FROM content_items WHERE user_telegram_id = ?
            ''', (user_telegram_id,))
            total_items = (await cursor.fetchone())[0]
            
            # Items by type
            cursor = await db.execute('''
                SELECT content_type, COUNT(*) 
                FROM content_items 
                WHERE user_telegram_id = ? 
                GROUP BY content_type
            ''', (user_telegram_id,))
            items_by_type = dict(await cursor.fetchall())
            
            # Recent activity (last 7 days)
            cursor = await db.execute('''
                SELECT COUNT(*) 
                FROM content_items 
                WHERE user_telegram_id = ? 
                AND created_at >= datetime('now', '-7 days')
            ''', (user_telegram_id,))
            recent_items = (await cursor.fetchone())[0]
            
            return {
                'total_items': total_items,
                'items_by_type': items_by_type,
                'recent_items': recent_items
            }