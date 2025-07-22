"""
Basic tests for RememBot components.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from pathlib import Path

from remembot.database import DatabaseManager
from remembot.content_processor import ContentProcessor
from remembot.classifier import ContentClassifier


class TestDatabaseManager:
    """Test database operations."""
    
    @pytest.fixture
    def db_manager(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name
        
        db_manager = DatabaseManager(db_path)
        yield db_manager
        
        # Cleanup
        os.unlink(db_path)
    
    @pytest.mark.asyncio
    async def test_store_and_search_content(self, db_manager):
        """Test storing and searching content."""
        # Store content
        item_id = await db_manager.store_content(
            user_telegram_id=12345,
            original_share="Test content",
            content_type="text",
            extracted_info="This is test content about Python programming"
        )
        
        assert item_id > 0
        
        # Search content
        results, total = await db_manager.search_content(12345, "Python")
        assert len(results) == 1
        assert total == 1
        assert results[0]['extracted_info'] == "This is test content about Python programming"
    
    @pytest.mark.asyncio
    async def test_user_stats(self, db_manager):
        """Test user statistics."""
        # Store some content
        await db_manager.store_content(12345, "url1", "url", extracted_info="Content 1")
        await db_manager.store_content(12345, "image1", "image", extracted_info="Content 2")
        await db_manager.store_content(67890, "text1", "text", extracted_info="Content 3")
        
        # Check stats for user 12345
        stats = await db_manager.get_user_stats(12345)
        assert stats['total_items'] == 2
        assert 'url' in stats['items_by_type']
        assert 'image' in stats['items_by_type']
        
        # Check stats for user 67890
        stats = await db_manager.get_user_stats(67890)
        assert stats['total_items'] == 1


class TestContentProcessor:
    """Test content processing."""
    
    @pytest_asyncio.fixture
    async def processor(self):
        """Create content processor."""
        processor = ContentProcessor()
        yield processor
        # Clean up session
        await processor.close()
    
    @pytest.mark.asyncio
    async def test_process_text(self, processor):
        """Test text processing."""
        result = await processor.process_text("This is a test message")
        
        assert result['content_type'] == 'text'
        assert result['extracted_info'] == "This is a test message"
        assert 'word_count' in result['metadata']
        assert result['metadata']['word_count'] == 5
    
    @pytest.mark.asyncio
    async def test_process_url_text(self, processor):
        """Test URL detection in text."""
        result = await processor.process_text("Check out https://example.com")
        
        assert result['content_type'] == 'url'
        assert 'https://example.com' in result['metadata']['url']
    
    def test_is_url(self, processor):
        """Test URL detection."""
        assert processor._is_url("https://example.com") == True
        assert processor._is_url("http://test.org") == True
        assert processor._is_url("not a url") == False
        assert processor._is_url("example.com") == False


class TestContentClassifier:
    """Test content classification."""
    
    @pytest.fixture
    def classifier(self):
        """Create content classifier."""
        return ContentClassifier()
    
    @pytest.mark.asyncio
    async def test_simple_classification(self, classifier):
        """Test simple keyword-based classification."""
        # Test computer science content
        result = await classifier.classify_content("Python programming tutorial")
        assert result['dewey_decimal'] in ["004", "005"], f"Expected 004 or 005, got {result['dewey_decimal']}"
        assert any('programming' in subject.lower() for subject in result['subjects']), f"Expected programming-related subject, got {result['subjects']}"
        
        # Test math content
        result = await classifier.classify_content("Mathematical equations and formulas")
        assert result['dewey_decimal'] == "510"
        assert any('math' in subject.lower() for subject in result['subjects']), f"Expected math-related subject, got {result['subjects']}"
        
        # Test general content - AI classification will be more confident than keyword matching
        result = await classifier.classify_content("Random text without specific topic")
        assert result['dewey_decimal'] in ["000", "800"]  # Could be general knowledge or literature
        # AI classification typically has higher confidence than keyword matching
        assert 0.0 <= result['confidence'] <= 1.0


if __name__ == "__main__":
    pytest.main([__file__])