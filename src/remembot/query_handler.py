"""
Query handler for RememBot.
Processes natural language queries and converts them to database searches.
"""

import logging
import os
from typing import Dict, List, Any, Optional
import json

from .database import DatabaseManager

# Optional OpenAI integration
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

logger = logging.getLogger(__name__)


class QueryHandler:
    """Handles user queries and converts them to database searches."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize query handler."""
        self.db_manager = db_manager
        self.openai_client = None
        if HAS_OPENAI and os.getenv('OPENAI_API_KEY'):
            self.openai_client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    async def process_query(self, user_id: int, query: str) -> List[Dict[str, Any]]:
        """Process a natural language query and return results."""
        # First, try a simple search
        results = await self.db_manager.search_content(user_id, query, limit=10)
        
        # If we have OpenAI available and no/few results, try AI-enhanced search
        if self.openai_client and len(results) < 3:
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
        if not self.openai_client or not results:
            return self._simple_summary(results, query)
        
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