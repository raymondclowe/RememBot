"""
Content classifier for RememBot.
Uses AI to classify content according to library standards.
"""

import logging
import os
from typing import Dict, List, Any, Optional
import json

# Optional AI integrations
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


class ContentClassifier:
    """Classifies content using AI and library standards."""
    
    def __init__(self):
        """Initialize content classifier."""
        self.openai_client = None
        self.openrouter_api_key = None
        
        # Set up OpenRouter if available
        if os.getenv('OPENROUTER_API_KEY'):
            self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        
        # Set up OpenAI as fallback if available
        if HAS_OPENAI and os.getenv('OPENAI_API_KEY'):
            self.openai_client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    async def classify_content(self, content: str) -> Dict[str, Any]:
        """Classify content according to library standards."""
        if not content or not content.strip():
            return {
                'dewey_decimal': None,
                'subjects': [],
                'confidence': 0.0,
                'classification_method': 'none'
            }
        
        # Try OpenRouter first if available
        if self.openrouter_api_key and HAS_AIOHTTP:
            try:
                return await self._openrouter_classify(content)
            except Exception as e:
                logger.warning(f"OpenRouter classification failed, falling back: {e}")
        
        # Fallback to OpenAI if available
        if self.openai_client:
            return await self._ai_classify(content)
        else:
            # Final fallback to simple keyword-based classification
            return self._simple_classify(content)
    
    async def _ai_classify(self, content: str) -> Dict[str, Any]:
        """Use AI to classify content."""
        try:
            # Truncate content if too long
            if len(content) > 3000:
                content = content[:3000] + "..."
            
            prompt = f"""
            Classify the following content according to library science standards.
            Provide a Dewey Decimal Classification (DDC) number and subject keywords.
            
            Content: {content}
            
            Please respond with a JSON object containing:
            - dewey_decimal: The most appropriate DDC number (3 digits)
            - subjects: Array of relevant subject keywords (max 5)
            - confidence: Confidence score from 0.0 to 1.0
            - reasoning: Brief explanation of the classification
            
            Example response:
            {{
                "dewey_decimal": "004",
                "subjects": ["computer science", "programming", "technology"],
                "confidence": 0.85,
                "reasoning": "Content discusses programming concepts and computer technology"
            }}
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a library science expert specializing in content classification."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.3
            )
            
            # Parse the response
            response_text = response.choices[0].message.content.strip()
            
            # Try to extract JSON from the response
            try:
                # Remove any markdown formatting
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]
                
                classification = json.loads(response_text)
                classification['classification_method'] = 'ai'
                return classification
                
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse AI classification response: {response_text}")
                return self._simple_classify(content)
        
        except Exception as e:
            logger.error(f"Error in AI classification: {e}")
            return self._simple_classify(content)
    
    async def _openrouter_classify(self, content: str) -> Dict[str, Any]:
        """Use OpenRouter API to classify content."""
        if len(content) > 3000:
            content = content[:3000] + "..."
        
        prompt = f"""
        Classify the following content according to library science standards.
        Provide a Dewey Decimal Classification (DDC) number and subject keywords.
        
        Content: {content}
        
        Please respond with a JSON object containing:
        - dewey_decimal: The most appropriate DDC number (3 digits)
        - subjects: Array of relevant subject keywords (max 5)
        - confidence: Confidence score from 0.0 to 1.0
        - reasoning: Brief explanation of the classification
        
        Example response:
        {{
            "dewey_decimal": "004",
            "subjects": ["computer science", "programming", "technology"],
            "confidence": 0.85,
            "reasoning": "Content discusses programming concepts and computer technology"
        }}
        """
        
        headers = {
            'Authorization': f'Bearer {self.openrouter_api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://github.com/raymondclowe/RememBot',
            'X-Title': 'RememBot Content Classification'
        }
        
        payload = {
            'model': 'openai/gpt-3.5-turbo',
            'messages': [
                {"role": "system", "content": "You are a library science expert specializing in content classification."},
                {"role": "user", "content": prompt}
            ],
            'max_tokens': 300,
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
                
                # Parse the response
                try:
                    # Remove any markdown formatting
                    if "```json" in response_text:
                        response_text = response_text.split("```json")[1].split("```")[0]
                    elif "```" in response_text:
                        response_text = response_text.split("```")[1].split("```")[0]
                    
                    classification = json.loads(response_text)
                    classification['classification_method'] = 'openrouter_ai'
                    return classification
                    
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse OpenRouter classification response: {response_text}")
                    # Fallback to simple classification
                    return self._simple_classify(content)
    
    def _simple_classify(self, content: str) -> Dict[str, Any]:
        """Simple keyword-based classification fallback."""
        content_lower = content.lower()
        
        # Define classification rules
        classifications = {
            # Computer Science & Technology (000-099)
            "004": {
                "keywords": ["programming", "code", "software", "computer", "algorithm", "python", "javascript", "github"],
                "subject": "computer science"
            },
            # Mathematics (500-599)
            "510": {
                "keywords": ["math", "mathematics", "equation", "formula", "calculation", "statistics"],
                "subject": "mathematics"
            },
            # Science (500-599)
            "500": {
                "keywords": ["science", "research", "experiment", "hypothesis", "theory", "physics", "chemistry", "biology"],
                "subject": "science"
            },
            # History (900-999)
            "900": {
                "keywords": ["history", "historical", "war", "ancient", "timeline", "past", "civilization"],
                "subject": "history"
            },
            # Literature (800-899)
            "800": {
                "keywords": ["book", "novel", "poetry", "literature", "author", "writing", "story"],
                "subject": "literature"
            },
            # Arts (700-799)
            "700": {
                "keywords": ["art", "painting", "music", "film", "movie", "photography", "design"],
                "subject": "arts"
            },
            # Business & Economics (330-339)
            "330": {
                "keywords": ["business", "economy", "economics", "finance", "money", "investment", "market"],
                "subject": "business"
            },
            # Health & Medicine (610-619)
            "610": {
                "keywords": ["health", "medicine", "medical", "doctor", "disease", "treatment", "hospital"],
                "subject": "medicine"
            },
            # Education (370-379)
            "370": {
                "keywords": ["education", "school", "teaching", "learning", "student", "university", "course"],
                "subject": "education"
            }
        }
        
        # Score each classification
        scores = {}
        matched_keywords = []
        
        for dewey_code, info in classifications.items():
            score = 0
            for keyword in info["keywords"]:
                if keyword in content_lower:
                    score += 1
                    matched_keywords.append(keyword)
            scores[dewey_code] = score
        
        # Find best match
        if scores and max(scores.values()) > 0:
            best_classification = max(scores.items(), key=lambda x: x[1])
            dewey_code = best_classification[0]
            confidence = min(best_classification[1] / 3.0, 1.0)  # Scale confidence
            
            return {
                'dewey_decimal': dewey_code,
                'subjects': list(set(matched_keywords[:5])),  # Remove duplicates, limit to 5
                'confidence': confidence,
                'classification_method': 'keyword_matching'
            }
        else:
            # No clear classification
            return {
                'dewey_decimal': "000",  # General works
                'subjects': ["general"],
                'confidence': 0.1,
                'classification_method': 'default'
            }