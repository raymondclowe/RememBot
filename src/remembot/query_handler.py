"""
Query handler for RememBot.
Processes natural language queries and converts them to database searches.
"""

import logging
import os
from typing import Dict, List, Any, Optional
import json

from .database import DatabaseManager
from .config import get_config

# Optional integrations
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

logger = logging.getLogger(__name__)


class QueryHandler:
    """Handles user queries and converts them to database searches."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize query handler."""
        self.db_manager = db_manager
        self.openai_client = None
        self.openrouter_api_key = None
        
        try:
            self.config = get_config()
            # Set up OpenRouter if available
            if self.config.openrouter_api_key:
                self.openrouter_api_key = self.config.openrouter_api_key
            
            # Set up OpenAI as fallback if available
            if HAS_OPENAI and self.config.openai_api_key:
                self.openai_client = openai.AsyncOpenAI(api_key=self.config.openai_api_key)
        except Exception:
            # Fallback for testing
            if os.getenv('OPENROUTER_API_KEY'):
                self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
            if HAS_OPENAI and os.getenv('OPENAI_API_KEY'):
                self.openai_client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    async def process_query(self, user_id: int, query: str) -> List[Dict[str, Any]]:
        """Process a natural language query and return results."""
        # First, try a simple search
        results = await self.db_manager.search_content(user_id, query, limit=10)
        
        # If we have AI available and no/few results, try AI-enhanced search
        if (self.openrouter_api_key and HAS_AIOHTTP) or self.openai_client:
            if len(results) < 3:
                enhanced_results = await self._ai_enhanced_search(user_id, query)
                if enhanced_results:
                    # Combine and deduplicate results
                    all_results = results + enhanced_results
                    seen_ids = set()
                    unique_results = []
                    for result in all_results:
                        if result['id'] not in seen_ids:
                            unique_results.append(result)
                            seen_ids.add(result['id'])
                    return unique_results
        
        return results
    
    async def _ai_enhanced_search(self, user_id: int, query: str) -> List[Dict[str, Any]]:
        """Use AI to generate better search terms and strategies."""
        # Try OpenRouter first if available
        if self.openrouter_api_key and HAS_AIOHTTP:
            try:
                return await self._openrouter_enhanced_search(user_id, query)
            except Exception as e:
                logger.warning(f"OpenRouter enhanced search failed, falling back: {e}")
        
        # Fallback to OpenAI if available
        if self.openai_client:
            return await self._openai_enhanced_search(user_id, query)
        
        return []
    
    async def _openrouter_enhanced_search(self, user_id: int, query: str) -> List[Dict[str, Any]]:
        """Use OpenRouter API to generate better search terms."""
        try:
            # First, get user stats to understand their content
            user_stats = await self.db_manager.get_user_stats(user_id)
            
            prompt = f"""
            A user has {user_stats['total_items']} items stored in their personal knowledge base.
            Their content types include: {', '.join(user_stats['items_by_type'].keys())}
            
            The user is searching for: "{query}"
            
            Generate 3-5 alternative search terms or keywords that might help find relevant content.
            Consider synonyms, related concepts, and different ways the content might be described.
            
            Respond with a JSON array of search terms:
            ["term1", "term2", "term3", ...]
            
            Focus on practical, concrete terms that would appear in stored content.
            """
            
            headers = {
                'Authorization': f'Bearer {self.openrouter_api_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://github.com/raymondclowe/RememBot',
                'X-Title': 'RememBot Enhanced Search'
            }
            
            payload = {
                'model': 'openai/gpt-3.5-turbo',
                'messages': [
                    {"role": "system", "content": "You are a search optimization expert helping users find content in their personal knowledge base."},
                    {"role": "user", "content": prompt}
                ],
                'max_tokens': 150,
                'temperature': 0.3
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://openrouter.ai/api/v1/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        raise Exception(f"OpenRouter API error: {response.status}")
                    
                    data = await response.json()
                    response_text = data['choices'][0]['message']['content'].strip()
                    
                    # Parse search terms
                    try:
                        # Remove any markdown formatting
                        if "```json" in response_text:
                            response_text = response_text.split("```json")[1].split("```")[0]
                        elif "```" in response_text:
                            response_text = response_text.split("```")[1].split("```")[0]
                        
                        search_terms = json.loads(response_text)
                        
                        # Perform searches with each term
                        all_results = []
                        for term in search_terms:
                            if isinstance(term, str) and term.strip():
                                results = await self.db_manager.search_content(user_id, term.strip(), limit=5)
                                all_results.extend(results)
                        
                        return all_results
                        
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse OpenRouter search terms: {response_text}")
                        return []
        
        except Exception as e:
            logger.error(f"Error in OpenRouter enhanced search: {e}")
            return []
    
    async def _openai_enhanced_search(self, user_id: int, query: str) -> List[Dict[str, Any]]:
        """Use OpenAI to generate better search terms and strategies."""
        try:
            # First, get user stats to understand their content
            user_stats = await self.db_manager.get_user_stats(user_id)
            
            prompt = f"""
            A user has {user_stats['total_items']} items stored in their personal knowledge base.
            Their content types include: {', '.join(user_stats['items_by_type'].keys())}
            
            The user is searching for: "{query}"
            
            Generate 3-5 alternative search terms or keywords that might help find relevant content.
            Consider synonyms, related concepts, and different ways the content might be described.
            
            Respond with a JSON array of search terms:
            ["term1", "term2", "term3", ...]
            
            Focus on practical, concrete terms that would appear in stored content.
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a search optimization expert helping users find content in their personal knowledge base."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.3
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parse search terms
            try:
                # Remove any markdown formatting
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]
                
                search_terms = json.loads(response_text)
                
                # Perform searches with each term
                all_results = []
                for term in search_terms:
                    if isinstance(term, str) and term.strip():
                        results = await self.db_manager.search_content(user_id, term.strip(), limit=5)
                        all_results.extend(results)
                
                return all_results
                
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse AI search terms: {response_text}")
                return []
        
        except Exception as e:
            logger.error(f"Error in AI-enhanced search: {e}")
            return []
    
    async def summarize_results(self, results: List[Dict[str, Any]], query: str) -> str:
        """Summarize search results using AI if available."""
        if not ((self.openrouter_api_key and HAS_AIOHTTP) or self.openai_client) or not results:
            return self._simple_summary(results, query)
        
        # Try OpenRouter first if available
        if self.openrouter_api_key and HAS_AIOHTTP:
            try:
                return await self._openrouter_summarize_results(results, query)
            except Exception as e:
                logger.warning(f"OpenRouter summarization failed, falling back: {e}")
        
        # Fallback to OpenAI if available
        if self.openai_client:
            return await self._openai_summarize_results(results, query)
        
        return self._simple_summary(results, query)
    
    async def _openrouter_summarize_results(self, results: List[Dict[str, Any]], query: str) -> str:
        """Summarize search results using OpenRouter API."""
        try:
            # Prepare content for summarization
            content_snippets = []
            for result in results[:5]:  # Limit to first 5 results
                snippet = {
                    'type': result['content_type'],
                    'content': result['extracted_info'][:200] + "..." if len(result['extracted_info']) > 200 else result['extracted_info'],
                    'date': result['created_at']
                }
                content_snippets.append(snippet)
            
            prompt = f"""
            A user searched for: "{query}"
            
            Here are the relevant items found in their knowledge base:
            
            {json.dumps(content_snippets, indent=2)}
            
            Please provide a concise summary of what was found, highlighting:
            1. The main themes or topics covered
            2. Key insights or information relevant to the query
            3. Any notable patterns or connections between the items
            
            Keep the summary under 200 words and focus on being helpful and informative.
            """
            
            headers = {
                'Authorization': f'Bearer {self.openrouter_api_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://github.com/raymondclowe/RememBot',
                'X-Title': 'RememBot Search Summary'
            }
            
            payload = {
                'model': 'openai/gpt-3.5-turbo',
                'messages': [
                    {"role": "system", "content": "You are a helpful assistant that summarizes search results from a personal knowledge base."},
                    {"role": "user", "content": prompt}
                ],
                'max_tokens': 250,
                'temperature': 0.5
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://openrouter.ai/api/v1/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        raise Exception(f"OpenRouter API error: {response.status}")
                    
                    data = await response.json()
                    return data['choices'][0]['message']['content'].strip()
        
        except Exception as e:
            logger.error(f"Error in OpenRouter summarization: {e}")
            return self._simple_summary(results, query)
    
    async def _openai_summarize_results(self, results: List[Dict[str, Any]], query: str) -> str:
        """Summarize search results using OpenAI if available."""
        
        try:
            # Prepare content for summarization
            content_snippets = []
            for result in results[:5]:  # Limit to first 5 results
                snippet = {
                    'type': result['content_type'],
                    'content': result['extracted_info'][:200] + "..." if len(result['extracted_info']) > 200 else result['extracted_info'],
                    'date': result['created_at']
                }
                content_snippets.append(snippet)
            
            prompt = f"""
            A user searched for: "{query}"
            
            Here are the relevant items found in their knowledge base:
            
            {json.dumps(content_snippets, indent=2)}
            
            Please provide a concise summary of what was found, highlighting:
            1. The main themes or topics covered
            2. Key insights or information relevant to the query
            3. Any notable patterns or connections between the items
            
            Keep the summary under 200 words and focus on being helpful and informative.
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes search results from a personal knowledge base."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=250,
                temperature=0.5
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"Error in AI summarization: {e}")
            return self._simple_summary(results, query)
    
    def _simple_summary(self, results: List[Dict[str, Any]], query: str) -> str:
        """Provide a simple summary without AI."""
        if not results:
            return f"No results found for '{query}'."
        
        # Count by content type
        type_counts = {}
        for result in results:
            content_type = result['content_type']
            type_counts[content_type] = type_counts.get(content_type, 0) + 1
        
        summary = f"Found {len(results)} item(s) for '{query}':\n"
        for content_type, count in type_counts.items():
            summary += f"• {count} {content_type} item(s)\n"
        
        return summary