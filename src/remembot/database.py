"""
Database manager for RememBot with FTS5 support and enhanced indexing.
Handles SQLite operations and schema management.
"""

import sqlite3
import aiosqlite
import logging
import json
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database operations for RememBot with FTS5 support."""
    
    def __init__(self, db_path: str):
        """Initialize database manager."""
        self.db_path = db_path
        self._connection_pool = None
        self._ensure_database_exists()
    
    def _ensure_database_exists(self):
        """Create database and tables if they don't exist."""
        # Create database directory if it doesn't exist
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Create tables using synchronous connection for initialization
        with sqlite3.connect(self.db_path) as conn:
            # Enable FTS5 extension if available
            try:
                conn.execute("SELECT fts5('test')")
                fts5_available = True
                logger.info("FTS5 extension is available")
            except sqlite3.OperationalError:
                fts5_available = False
                logger.warning("FTS5 extension not available, falling back to basic search")
            
            # Create main content table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS content_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_telegram_id INTEGER NOT NULL,
                    original_share TEXT NOT NULL,
                    metadata TEXT,
                    extracted_info TEXT,
                    taxonomy TEXT,
                    content_type TEXT,
                    source_platform TEXT,
                    processing_time_ms REAL,
                    content_hash TEXT,
                    version INTEGER DEFAULT 1,
                    parse_status TEXT DEFAULT 'pending',
                    parse_error TEXT,
                    parse_attempts INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Ensure all expected columns exist
            expected_columns = {
                'source_platform': 'TEXT',
                'processing_time_ms': 'REAL',
                'content_hash': 'TEXT',
                'version': 'INTEGER DEFAULT 1',
                'parse_status': 'TEXT DEFAULT \'pending\'',
                'parse_error': 'TEXT',
                'parse_attempts': 'INTEGER DEFAULT 0'
            }
            cursor = conn.execute("PRAGMA table_info(content_items)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            for col, coltype in expected_columns.items():
                if col not in existing_columns:
                    logger.info(f"Adding missing column '{col}' to content_items table.")
                    conn.execute(f"ALTER TABLE content_items ADD COLUMN {col} {coltype}")
            
            # Create user activity tracking table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_telegram_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    content_item_id INTEGER,
                    query TEXT,
                    result_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (content_item_id) REFERENCES content_items (id)
                )
            ''')
            
            # Create content relationships table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS content_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_item_id INTEGER NOT NULL,
                    to_item_id INTEGER NOT NULL,
                    relationship_type TEXT NOT NULL,
                    confidence_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (from_item_id) REFERENCES content_items (id),
                    FOREIGN KEY (to_item_id) REFERENCES content_items (id),
                    UNIQUE(from_item_id, to_item_id, relationship_type)
                )
            ''')
            
            # Create FTS5 table if available
            if fts5_available:
                conn.execute('''
                    CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
                        content_item_id UNINDEXED,
                        title,
                        extracted_info,
                        tags,
                        content=content_items,
                        content_rowid=id
                    )
                ''')
                
                # Create triggers to keep FTS table in sync
                conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS content_fts_insert AFTER INSERT ON content_items BEGIN
                        INSERT INTO content_fts(content_item_id, extracted_info)
                        VALUES (new.id, COALESCE(new.extracted_info, ''));
                    END
                ''')
                
                conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS content_fts_delete AFTER DELETE ON content_items BEGIN
                        DELETE FROM content_fts WHERE content_item_id = old.id;
                    END
                ''')
                
                conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS content_fts_update AFTER UPDATE ON content_items BEGIN
                        UPDATE content_fts 
                        SET extracted_info = COALESCE(new.extracted_info, '')
                        WHERE content_item_id = new.id;
                    END
                ''')
            
            # Create indexes
            indexes = [
                ('idx_user_telegram_id', 'content_items(user_telegram_id)'),
                ('idx_content_type', 'content_items(content_type)'),
                ('idx_created_at', 'content_items(created_at)'),
                ('idx_updated_at', 'content_items(updated_at)'),
                ('idx_source_platform', 'content_items(source_platform)'),
                ('idx_content_hash', 'content_items(content_hash)'),
                ('idx_user_activity_user', 'user_activity(user_telegram_id)'),
                ('idx_user_activity_created', 'user_activity(created_at)'),
                ('idx_relationships_from', 'content_relationships(from_item_id)'),
                ('idx_relationships_to', 'content_relationships(to_item_id)'),
            ]
            
            for index_name, index_def in indexes:
                conn.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {index_def}')
            
            # Store FTS5 availability
            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                INSERT OR REPLACE INTO system_config (key, value) 
                VALUES ('fts5_available', ?)
            ''', (str(fts5_available),))
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path} (FTS5: {fts5_available})")
    
    async def _get_connection(self):
        """Get database connection."""
        return aiosqlite.connect(self.db_path)
    
    async def is_fts5_available(self) -> bool:
        """Check if FTS5 is available."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM system_config WHERE key = 'fts5_available'"
            )
            result = await cursor.fetchone()
            return result and result[0] == 'True'
    
    async def store_content(
        self, 
        user_telegram_id: int,
        original_share: str,
        content_type: str,
        metadata: Optional[str] = None,
        extracted_info: Optional[str] = None,
        taxonomy: Optional[str] = None,
        processing_time_ms: Optional[float] = None,
        parse_status: str = 'pending'
    ) -> int:
        """Store a content item in the database with enhanced metadata."""
        async with aiosqlite.connect(self.db_path) as db:
            # Parse metadata to extract additional fields
            source_platform = None
            content_hash = None
            
            if metadata:
                try:
                    meta_dict = json.loads(metadata)
                    # Detect source platform from URL or metadata
                    if 'url' in meta_dict:
                        source_platform = self._detect_source_platform(meta_dict['url'])
                    # Generate content hash for duplicate detection
                    content_text = extracted_info or original_share
                    content_hash = str(hash(content_text.strip().lower())) if content_text else None
                except json.JSONDecodeError:
                    logger.warning(f"Invalid metadata JSON for user {user_telegram_id}")
            
            cursor = await db.execute('''
                INSERT INTO content_items 
                (user_telegram_id, original_share, content_type, metadata, extracted_info, 
                 taxonomy, source_platform, processing_time_ms, content_hash, parse_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_telegram_id, original_share, content_type, metadata, extracted_info, 
                  taxonomy, source_platform, processing_time_ms, content_hash, parse_status))
            
            await db.commit()
            item_id = cursor.lastrowid
            
            # Log user activity
            await self._log_user_activity(db, user_telegram_id, 'store_content', item_id)
            
            logger.info(f"Stored content item {item_id} for user {user_telegram_id} "
                       f"(type: {content_type}, platform: {source_platform})")
            return item_id
    
    def _detect_source_platform(self, url: str) -> Optional[str]:
        """Detect source platform from URL."""
        if not url:
            return None
        
        url_lower = url.lower()
        platforms = {
            'twitter.com': 'twitter',
            'x.com': 'twitter',
            'reddit.com': 'reddit',
            'youtube.com': 'youtube',
            'youtu.be': 'youtube',
            'github.com': 'github',
            'medium.com': 'medium',
            'linkedin.com': 'linkedin',
            'stackoverflow.com': 'stackoverflow',
            'wikipedia.org': 'wikipedia',
            'news.ycombinator.com': 'hackernews',
            'arxiv.org': 'arxiv'
        }
        
        for domain, platform in platforms.items():
            if domain in url_lower:
                return platform
        
        return 'web'
    
    async def _log_user_activity(
        self, 
        db: aiosqlite.Connection, 
        user_telegram_id: int, 
        action_type: str, 
        content_item_id: Optional[int] = None,
        query: Optional[str] = None,
        result_count: Optional[int] = None
    ):
        """Log user activity for analytics."""
        await db.execute('''
            INSERT INTO user_activity 
            (user_telegram_id, action_type, content_item_id, query, result_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_telegram_id, action_type, content_item_id, query, result_count))
    
    async def get_user_content(
        self, 
        user_telegram_id: int,
        content_type: Optional[str] = None,
        source_platform: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get user's content items with filtering and pagination."""
        async with aiosqlite.connect(self.db_path) as db:
            # Build base query
            base_query = '''
                SELECT id, original_share, content_type, metadata, extracted_info, 
                       taxonomy, source_platform, created_at
                FROM content_items 
                WHERE user_telegram_id = ?
            '''
            
            params = [user_telegram_id]
            
            # Add optional filters
            if content_type:
                base_query += ' AND content_type = ?'
                params.append(content_type)
            
            if source_platform:
                base_query += ' AND source_platform = ?'
                params.append(source_platform)
            
            # Add ordering and pagination
            query_with_order = base_query + ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            # Execute query
            cursor = await db.execute(query_with_order, params)
            rows = await cursor.fetchall()
            
            # Get total count
            count_query = base_query.replace(
                'SELECT id, original_share, content_type, metadata, extracted_info, taxonomy, source_platform, created_at',
                'SELECT COUNT(*)'
            )
            cursor = await db.execute(count_query, params[:-2])  # Exclude limit and offset
            total = (await cursor.fetchone())[0]
            
            # Convert to dictionaries
            columns = ['id', 'original_share', 'content_type', 'metadata', 'extracted_info', 
                      'taxonomy', 'source_platform', 'created_at']
            results = [dict(zip(columns, row)) for row in rows]
            
            return results, total
    
    async def search_content(
        self, 
        user_telegram_id: int, 
        query: str,
        content_type: Optional[str] = None,
        source_platform: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Search for content items with FTS5 support and ranking."""
        # If no search query, just get user content
        if not query or not query.strip():
            return await self.get_user_content(user_telegram_id, content_type, source_platform, limit, offset)
        
        start_time = time.time()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Log search activity
            await self._log_user_activity(db, user_telegram_id, 'search', query=query)
            
            fts5_available = await self.is_fts5_available()
            
            try:
                if fts5_available and len(query.strip()) > 2:
                    # Use FTS5 for advanced search
                    results, total = await self._search_with_fts5(
                        db, user_telegram_id, query, content_type, source_platform, limit, offset
                    )
                else:
                    # Fallback to basic LIKE search
                    results, total = await self._search_with_like(
                        db, user_telegram_id, query, content_type, source_platform, limit, offset
                    )
            except Exception as e:
                logger.warning(f"FTS5 search failed, falling back to LIKE search: {e}")
                # Fallback to basic LIKE search
                results, total = await self._search_with_like(
                    db, user_telegram_id, query, content_type, source_platform, limit, offset
                )
            
            search_time = (time.time() - start_time) * 1000
            
            # Update activity log with result count
            await self._log_user_activity(db, user_telegram_id, 'search_result', 
                                        result_count=len(results))
            
            logger.info(f"Found {len(results)}/{total} items for query '{query}' "
                       f"by user {user_telegram_id} in {search_time:.1f}ms")
            return results, total
    
    async def _search_with_fts5(
        self, 
        db: aiosqlite.Connection,
        user_telegram_id: int, 
        query: str,
        content_type: Optional[str] = None,
        source_platform: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Search using FTS5 with ranking."""
        # Prepare FTS5 query (escape special characters)
        fts_query = query.replace('"', '""')
        
        # Build base query with JOIN to FTS5 table
        base_query = '''
            SELECT ci.id, ci.original_share, ci.content_type, ci.metadata, 
                   ci.extracted_info, ci.taxonomy, ci.source_platform, ci.created_at,
                   content_fts.rank
            FROM content_items ci
            JOIN content_fts ON ci.id = content_fts.content_item_id
            WHERE ci.user_telegram_id = ? 
            AND content_fts MATCH ?
        '''
        
        params = [user_telegram_id, fts_query]
        
        # Add optional filters
        if content_type:
            base_query += ' AND ci.content_type = ?'
            params.append(content_type)
        
        if source_platform:
            base_query += ' AND ci.source_platform = ?'
            params.append(source_platform)
        
        # Add ordering and pagination
        query_with_order = base_query + ' ORDER BY content_fts.rank, ci.created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        # Execute search query
        cursor = await db.execute(query_with_order, params)
        rows = await cursor.fetchall()
        
        # Get total count
        count_query = base_query.replace(
            'SELECT ci.id, ci.original_share, ci.content_type, ci.metadata, ci.extracted_info, ci.taxonomy, ci.source_platform, ci.created_at, cf.rank',
            'SELECT COUNT(*)'
        )
        cursor = await db.execute(count_query, params[:-2])  # Exclude limit and offset
        total = (await cursor.fetchone())[0]
        
        # Convert to dictionaries
        columns = ['id', 'original_share', 'content_type', 'metadata', 'extracted_info', 
                  'taxonomy', 'source_platform', 'created_at', 'rank']
        results = [dict(zip(columns, row)) for row in rows]
        
        return results, total
    
    async def _search_with_like(
        self, 
        db: aiosqlite.Connection,
        user_telegram_id: int, 
        query: str,
        content_type: Optional[str] = None,
        source_platform: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fallback search using LIKE operator."""
        search_term = f"%{query}%"
        
        base_query = '''
            SELECT id, original_share, content_type, metadata, extracted_info, 
                   taxonomy, source_platform, created_at
            FROM content_items 
            WHERE user_telegram_id = ? 
            AND (extracted_info LIKE ? OR original_share LIKE ?)
        '''
        
        params = [user_telegram_id, search_term, search_term]
        
        # Add optional filters
        if content_type:
            base_query += ' AND content_type = ?'
            params.append(content_type)
        
        if source_platform:
            base_query += ' AND source_platform = ?'
            params.append(source_platform)
        
        # Add ordering and pagination
        query_with_order = base_query + ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        # Execute search query
        cursor = await db.execute(query_with_order, params)
        rows = await cursor.fetchall()
        
        # Get total count
        count_query = base_query.replace(
            'SELECT id, original_share, content_type, metadata, extracted_info, taxonomy, source_platform, created_at',
            'SELECT COUNT(*)'
        )
        cursor = await db.execute(count_query, params[:-2])  # Exclude limit and offset
        total = (await cursor.fetchone())[0]
        
        # Convert to dictionaries  
        columns = ['id', 'original_share', 'content_type', 'metadata', 'extracted_info', 
                  'taxonomy', 'source_platform', 'created_at']
        results = [dict(zip(columns, row)) for row in rows]
        
        return results, total
    
    async def get_user_stats(self, user_telegram_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics for a user's stored content."""
        async with aiosqlite.connect(self.db_path) as db:
            stats = {}
            
            # Total items
            cursor = await db.execute('''
                SELECT COUNT(*) FROM content_items WHERE user_telegram_id = ?
            ''', (user_telegram_id,))
            stats['total_items'] = (await cursor.fetchone())[0]
            
            # Items by type
            cursor = await db.execute('''
                SELECT content_type, COUNT(*) 
                FROM content_items 
                WHERE user_telegram_id = ? 
                GROUP BY content_type
                ORDER BY COUNT(*) DESC
            ''', (user_telegram_id,))
            stats['items_by_type'] = dict(await cursor.fetchall())
            
            # Items by source platform
            cursor = await db.execute('''
                SELECT COALESCE(source_platform, 'unknown') as platform, COUNT(*) 
                FROM content_items 
                WHERE user_telegram_id = ? 
                GROUP BY source_platform
                ORDER BY COUNT(*) DESC
            ''', (user_telegram_id,))
            stats['items_by_platform'] = dict(await cursor.fetchall())
            
            # Recent activity (last 7 days)
            cursor = await db.execute('''
                SELECT COUNT(*) 
                FROM content_items 
                WHERE user_telegram_id = ? 
                AND created_at >= datetime('now', '-7 days')
            ''', (user_telegram_id,))
            stats['recent_items'] = (await cursor.fetchone())[0]
            
            # Content growth over time (last 30 days)
            cursor = await db.execute('''
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM content_items 
                WHERE user_telegram_id = ? 
                AND created_at >= datetime('now', '-30 days')
                GROUP BY DATE(created_at)
                ORDER BY date
            ''', (user_telegram_id,))
            stats['daily_activity'] = dict(await cursor.fetchall())
            
            # Search activity
            cursor = await db.execute('''
                SELECT COUNT(*) 
                FROM user_activity 
                WHERE user_telegram_id = ? 
                AND action_type = 'search'
                AND created_at >= datetime('now', '-7 days')
            ''', (user_telegram_id,))
            stats['recent_searches'] = (await cursor.fetchone())[0]
            
            # Average processing time
            cursor = await db.execute('''
                SELECT AVG(processing_time_ms) 
                FROM content_items 
                WHERE user_telegram_id = ? 
                AND processing_time_ms IS NOT NULL
            ''', (user_telegram_id,))
            avg_time = (await cursor.fetchone())[0]
            stats['avg_processing_time_ms'] = round(avg_time, 2) if avg_time else None
            
            return stats
    
    async def get_content_by_id(self, user_telegram_id: int, content_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific content item by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, original_share, content_type, metadata, extracted_info, 
                       taxonomy, source_platform, processing_time_ms, created_at, updated_at
                FROM content_items 
                WHERE id = ? AND user_telegram_id = ?
            ''', (content_id, user_telegram_id))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
    
    async def update_content(
        self, 
        user_telegram_id: int, 
        content_id: int, 
        extracted_info: Optional[str] = None,
        taxonomy: Optional[str] = None
    ) -> bool:
        """Update an existing content item."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if item exists and belongs to user
            cursor = await db.execute('''
                SELECT id, version FROM content_items 
                WHERE id = ? AND user_telegram_id = ?
            ''', (content_id, user_telegram_id))
            
            result = await cursor.fetchone()
            if not result:
                return False
            
            current_version = result[1]
            
            # Update the item
            cursor = await db.execute('''
                UPDATE content_items 
                SET extracted_info = COALESCE(?, extracted_info),
                    taxonomy = COALESCE(?, taxonomy),
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_telegram_id = ?
            ''', (extracted_info, taxonomy, content_id, user_telegram_id))
            
            await db.commit()
            
            # Log activity
            await self._log_user_activity(db, user_telegram_id, 'update_content', content_id)
            
            logger.info(f"Updated content item {content_id} for user {user_telegram_id} "
                       f"(version {current_version} -> {current_version + 1})")
            return True
    
    async def delete_content(self, user_telegram_id: int, content_id: int) -> bool:
        """Delete a content item."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                DELETE FROM content_items 
                WHERE id = ? AND user_telegram_id = ?
            ''', (content_id, user_telegram_id))
            
            await db.commit()
            deleted = cursor.rowcount > 0
            
            if deleted:
                # Log activity
                await self._log_user_activity(db, user_telegram_id, 'delete_content', content_id)
                logger.info(f"Deleted content item {content_id} for user {user_telegram_id}")
            
            return deleted
    
    async def find_similar_content(
        self, 
        user_telegram_id: int, 
        content_hash: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Find content with similar hash (potential duplicates)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, original_share, content_type, created_at
                FROM content_items 
                WHERE user_telegram_id = ? AND content_hash = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_telegram_id, content_hash, limit))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    async def get_user_activity(
        self, 
        user_telegram_id: int, 
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get user activity history."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT action_type, content_item_id, query, result_count, created_at
                FROM user_activity 
                WHERE user_telegram_id = ? 
                AND created_at >= datetime('now', '-{} days')
                ORDER BY created_at DESC
                LIMIT 100
            '''.format(days), (user_telegram_id,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    async def store_web_token(self, user_telegram_id: int, token: str, expiry: int):
        """Store a web authentication token for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            # First check if web_tokens table exists, create if not
            await db.execute('''
                CREATE TABLE IF NOT EXISTS web_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_telegram_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expiry INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_at TIMESTAMP NULL
                )
            ''')
            
            # Clean up expired tokens for this user
            await db.execute('''
                DELETE FROM web_tokens 
                WHERE user_telegram_id = ? AND expiry < ?
            ''', (user_telegram_id, int(time.time())))
            
            # Store the new token
            await db.execute('''
                INSERT INTO web_tokens (user_telegram_id, token, expiry)
                VALUES (?, ?, ?)
            ''', (user_telegram_id, token, expiry))
            
            await db.commit()
            logger.info(f"Stored web token for user {user_telegram_id}")
    
    async def validate_web_token(self, token: str, user_telegram_id: int) -> bool:
        """Validate a web authentication token."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, expiry FROM web_tokens 
                WHERE token = ? AND user_telegram_id = ?
            ''', (token, user_telegram_id))
            
            row = await cursor.fetchone()
            if not row:
                return False
            
            token_id, expiry = row
            current_time = int(time.time())
            
            if expiry < current_time:
                # Token expired, clean it up
                await db.execute('DELETE FROM web_tokens WHERE id = ?', (token_id,))
                await db.commit()
                return False
            
            # Update the last used time (but don't mark as single-use anymore)
            await db.execute('''
                UPDATE web_tokens SET used_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (token_id,))
            await db.commit()
            
            return True
    
    async def get_pending_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get content items that need processing."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, user_telegram_id, original_share, content_type, metadata, 
                       created_at, parse_attempts
                FROM content_items 
                WHERE parse_status = 'pending' 
                AND parse_attempts < 3
                ORDER BY created_at ASC
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    async def update_parse_status(
        self, 
        item_id: int, 
        status: str, 
        extracted_info: Optional[str] = None,
        taxonomy: Optional[str] = None,
        processing_time_ms: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update the parsing status of an item."""
        async with aiosqlite.connect(self.db_path) as db:
            if status == 'processing':
                # Mark as currently being processed
                await db.execute('''
                    UPDATE content_items 
                    SET parse_status = 'processing', 
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (item_id,))
            elif status == 'complete':
                # Mark as completed with results
                await db.execute('''
                    UPDATE content_items 
                    SET parse_status = 'complete',
                        extracted_info = COALESCE(?, extracted_info),
                        taxonomy = COALESCE(?, taxonomy),
                        processing_time_ms = COALESCE(?, processing_time_ms),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (extracted_info, taxonomy, processing_time_ms, item_id))
            elif status == 'error':
                # Mark as errored and increment attempts
                await db.execute('''
                    UPDATE content_items 
                    SET parse_status = 'error',
                        parse_error = ?,
                        parse_attempts = parse_attempts + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (error_message, item_id))
            elif status == 'retry':
                # Reset to pending for retry (with incremented attempts)
                await db.execute('''
                    UPDATE content_items 
                    SET parse_status = 'pending',
                        parse_attempts = parse_attempts + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (item_id,))
            
            await db.commit()
            return True
    
    async def get_parse_stats(self) -> Dict[str, int]:
        """Get parsing statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            stats = {}
            
            # Count by status
            cursor = await db.execute('''
                SELECT parse_status, COUNT(*) 
                FROM content_items 
                GROUP BY parse_status
            ''')
            status_counts = dict(await cursor.fetchall())
            
            stats.update({
                'pending': status_counts.get('pending', 0),
                'processing': status_counts.get('processing', 0),
                'complete': status_counts.get('complete', 0),
                'error': status_counts.get('error', 0)
            })
            
            # Failed items (3+ attempts)
            cursor = await db.execute('''
                SELECT COUNT(*) FROM content_items 
                WHERE parse_attempts >= 3 AND parse_status IN ('error', 'pending')
            ''')
            stats['failed'] = (await cursor.fetchone())[0]
            
            return stats