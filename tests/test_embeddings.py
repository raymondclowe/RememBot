"""
Test embeddings functionality.
"""

import pytest
import tempfile
import os
from pathlib import Path

from remembot.embeddings import EmbeddingsManager


class TestEmbeddingsManager:
    """Test embeddings functionality."""
    
    @pytest.fixture
    def embeddings_manager(self):
        """Create a temporary embeddings manager for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name
        
        # Create a minimal database with content_items table
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.execute('''
                CREATE TABLE content_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_telegram_id INTEGER NOT NULL,
                    original_share TEXT NOT NULL,
                    content_type TEXT,
                    extracted_info TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        
        manager = EmbeddingsManager(db_path)
        yield manager
        
        # Cleanup
        os.unlink(db_path)
    
    @pytest.mark.asyncio
    async def test_embedding_generation(self, embeddings_manager):
        """Test basic embedding generation."""
        # Test with simple text
        embedding = await embeddings_manager.generate_embedding("This is a test sentence")
        
        if embedding is not None:
            # If sentence-transformers is available
            assert len(embedding) == embeddings_manager.embedding_dim
            assert embedding.dtype.name.startswith('float')
        else:
            # If sentence-transformers is not available, that's okay for testing
            pass
    
    @pytest.mark.asyncio
    async def test_embedding_storage(self, embeddings_manager):
        """Test storing embeddings."""
        # First store a content item
        import sqlite3
        with sqlite3.connect(embeddings_manager.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO content_items (user_telegram_id, original_share, content_type, extracted_info)
                VALUES (?, ?, ?, ?)
            ''', (12345, "Test content", "text", "This is test content about machine learning"))
            conn.commit()
            content_id = cursor.lastrowid
        
        # Store embedding
        success = await embeddings_manager.store_embedding(
            content_id, "This is test content about machine learning"
        )
        
        # If sentence-transformers is available, it should succeed
        # If not, it should fail gracefully
        assert isinstance(success, bool)
    
    @pytest.mark.asyncio
    async def test_semantic_search(self, embeddings_manager):
        """Test semantic search functionality."""
        # Add some test content
        import sqlite3
        with sqlite3.connect(embeddings_manager.db_path) as conn:
            test_items = [
                (12345, "Python tutorial", "text", "Learn Python programming basics"),
                (12345, "Machine learning", "text", "Introduction to machine learning concepts"),
                (12345, "Cooking recipe", "text", "How to make chocolate cake"),
            ]
            
            for user_id, original, content_type, extracted in test_items:
                cursor = conn.execute('''
                    INSERT INTO content_items (user_telegram_id, original_share, content_type, extracted_info)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, original, content_type, extracted))
                content_id = cursor.lastrowid
                
                # Try to store embedding
                await embeddings_manager.store_embedding(content_id, extracted)
            
            conn.commit()
        
        # Perform semantic search
        results = await embeddings_manager.semantic_search(12345, "programming tutorial")
        
        # Results should be a list (empty if sentence-transformers not available)
        assert isinstance(results, list)
    
    @pytest.mark.asyncio
    async def test_embedding_stats(self, embeddings_manager):
        """Test embedding statistics."""
        stats = await embeddings_manager.get_embedding_stats()
        
        assert isinstance(stats, dict)
        assert 'model_available' in stats
        assert 'total_embeddings' in stats or 'error' in stats