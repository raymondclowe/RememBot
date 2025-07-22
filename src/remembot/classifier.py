"""
Enhanced content classifier for RememBot with library science standards.
Uses AI to classify content according to Dewey Decimal and Library of Congress systems.
"""

import logging
import os
from typing import Dict, List, Any, Optional, Tuple
import json
import re
import asyncio

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

from .config import get_config

logger = logging.getLogger(__name__)


class DeweyDecimalClassifier:
    """Dewey Decimal Classification system implementation."""
    
    # Comprehensive DDC main classes and subdivisions
    DDC_SYSTEM = {
        "000": {
            "name": "Computer science, information, and general works",
            "subdivisions": {
                "000": "Computer science, knowledge, and general works",
                "010": "Bibliographies",
                "020": "Library and information sciences",
                "030": "Encyclopedias and books of facts",
                "040": "Not assigned or no longer used",
                "050": "Magazines, journals, and serials",
                "060": "Associations, organizations, and museums",
                "070": "Documentary media, journalism, and publishing",
                "080": "General collections",
                "090": "Manuscripts and rare books"
            }
        },
        "100": {
            "name": "Philosophy and psychology", 
            "subdivisions": {
                "100": "Philosophy",
                "110": "Metaphysics",
                "120": "Epistemology",
                "130": "Parapsychology and occultism",
                "140": "Philosophical schools of thought",
                "150": "Psychology",
                "160": "Philosophical logic",
                "170": "Ethics",
                "180": "Ancient, medieval, eastern philosophy",
                "190": "Modern western philosophy"
            }
        },
        "200": {
            "name": "Religion",
            "subdivisions": {
                "200": "Religion",
                "210": "Philosophy and theory of religion",
                "220": "The Bible",
                "230": "Christianity and Christian theology",
                "240": "Christian practice and observance",
                "250": "Christian pastoral practice and religious orders",
                "260": "Christian organization, social work, and worship",
                "270": "History of Christianity",
                "280": "Christian denominations",
                "290": "Other religions"
            }
        },
        "300": {
            "name": "Social sciences",
            "subdivisions": {
                "300": "Social sciences, sociology, and anthropology",
                "310": "Statistics",
                "320": "Political science",
                "330": "Economics",
                "340": "Law",
                "350": "Public administration and military science",
                "360": "Social problems and social welfare",
                "370": "Education",
                "380": "Commerce, communications, and transportation",
                "390": "Customs and folklore"
            }
        },
        "400": {
            "name": "Language",
            "subdivisions": {
                "400": "Language",
                "410": "Linguistics",
                "420": "English and Old English languages",
                "430": "German and related languages",
                "440": "French and related languages",
                "450": "Italian, Romanian, and related languages",
                "460": "Spanish and Portuguese languages",
                "470": "Latin and Italic languages",
                "480": "Classical and modern Greek languages",
                "490": "Other languages"
            }
        },
        "500": {
            "name": "Pure sciences",
            "subdivisions": {
                "500": "Science and mathematics",
                "510": "Mathematics",
                "520": "Astronomy",
                "530": "Physics",
                "540": "Chemistry",
                "550": "Earth sciences and geology",
                "560": "Fossils and prehistoric life",
                "570": "Life sciences and biology",
                "580": "Plants (Botany)",
                "590": "Animals (Zoology)"
            }
        },
        "600": {
            "name": "Technology and applied sciences",
            "subdivisions": {
                "600": "Technology",
                "610": "Medicine and health",
                "620": "Engineering",
                "630": "Agriculture",
                "640": "Home and family living",
                "650": "Management and public relations",
                "660": "Chemical engineering",
                "670": "Manufacturing",
                "680": "Manufacture for specific uses",
                "690": "Building and construction"
            }
        },
        "700": {
            "name": "Arts and recreation",
            "subdivisions": {
                "700": "Arts",
                "710": "Landscaping and area planning",
                "720": "Architecture",
                "730": "Sculpture, ceramics, and metalwork",
                "740": "Drawing and decorative arts",
                "750": "Painting",
                "760": "Graphic arts",
                "770": "Photography and computer art",
                "780": "Music",
                "790": "Sports, games, and entertainment"
            }
        },
        "800": {
            "name": "Literature",
            "subdivisions": {
                "800": "Literature, rhetoric, and criticism",
                "810": "American literature in English",
                "820": "English and Old English literatures",
                "830": "German and related literatures",
                "840": "French and related literatures",
                "850": "Italian, Romanian, and related literatures",
                "860": "Spanish and Portuguese literatures",
                "870": "Latin and Italic literatures",
                "880": "Classical and modern Greek literatures",
                "890": "Other literatures"
            }
        },
        "900": {
            "name": "History and geography",
            "subdivisions": {
                "900": "History",
                "910": "Geography and travel",
                "920": "Biography and genealogy",
                "930": "History of ancient world (to ca. 499)",
                "940": "History of Europe",
                "950": "History of Asia",
                "960": "History of Africa",
                "970": "History of North America",
                "980": "History of South America",
                "990": "History of other areas"
            }
        }
    }
    
    # Keyword patterns for classification
    KEYWORD_PATTERNS = {
        "000": ["computer", "programming", "software", "technology", "data", "information", "internet", "web", "code", "algorithm", "digital"],
        "004": ["programming", "coding", "software", "development", "python", "javascript", "java", "c++", "algorithm", "debugging"],
        "005": ["computer science", "software engineering", "data structures", "machine learning", "ai", "artificial intelligence"],
        "020": ["library", "information science", "cataloging", "metadata"],
        "070": ["journalism", "news", "media", "publishing", "documentary"],
        "100": ["philosophy", "ethics", "morality", "consciousness", "existence", "metaphysics"],
        "150": ["psychology", "behavior", "mental health", "cognitive", "therapy", "mind"],
        "200": ["religion", "spiritual", "faith", "church", "prayer", "biblical", "theology"],
        "300": ["society", "social", "culture", "anthropology", "sociology"],
        "320": ["politics", "government", "democracy", "policy", "election", "political"],
        "330": ["economics", "economy", "finance", "money", "business", "market", "trade"],
        "340": ["law", "legal", "court", "justice", "rights", "constitution", "legislation"],
        "370": ["education", "learning", "teaching", "school", "university", "academic"],
        "400": ["language", "linguistic", "grammar", "translation", "communication"],
        "500": ["science", "scientific", "research", "study", "analysis"],
        "510": ["mathematics", "math", "algebra", "geometry", "calculus", "statistics"],
        "520": ["astronomy", "space", "planets", "stars", "universe", "cosmic"],
        "530": ["physics", "quantum", "mechanics", "energy", "relativity"],
        "540": ["chemistry", "chemical", "molecular", "reaction", "compound"],
        "550": ["geology", "earth", "climate", "weather", "environment"],
        "570": ["biology", "life", "organism", "evolution", "genetics", "biodiversity"],
        "610": ["medicine", "health", "medical", "doctor", "disease", "treatment", "therapy"],
        "620": ["engineering", "mechanical", "electrical", "civil", "structural"],
        "630": ["agriculture", "farming", "crops", "livestock", "food production"],
        "650": ["management", "business", "leadership", "organization", "strategy"],
        "700": ["art", "artistic", "creative", "design", "aesthetic"],
        "720": ["architecture", "building", "construction", "design"],
        "750": ["painting", "drawing", "visual art", "canvas"],
        "780": ["music", "musical", "song", "composer", "instrument", "melody"],
        "790": ["sports", "games", "recreation", "entertainment", "hobby"],
        "800": ["literature", "poetry", "novel", "writing", "author", "literary"],
        "900": ["history", "historical", "past", "ancient", "civilization"],
        "910": ["geography", "travel", "location", "place", "country", "city"],
        "920": ["biography", "life story", "memoir", "person", "individual"]
    }
    
    def classify_by_keywords(self, content: str) -> Tuple[str, float]:
        """Classify content using keyword matching."""
        content_lower = content.lower()
        word_count = len(content.split())
        
        best_match = "000"
        best_score = 0.0
        
        for ddc_code, keywords in self.KEYWORD_PATTERNS.items():
            matches = sum(1 for keyword in keywords if keyword in content_lower)
            if matches > 0:
                # Score based on keyword density
                score = matches / len(keywords) * (matches / max(word_count, 1)) * 10
                if score > best_score:
                    best_score = score
                    best_match = ddc_code
        
        # Normalize confidence to 0-1 range
        confidence = min(best_score, 0.8)  # Cap at 0.8 for keyword-based classification
        
        return best_match, confidence
    
    def get_classification_info(self, ddc_code: str) -> Dict[str, Any]:
        """Get detailed classification information for a DDC code."""
        main_class = ddc_code[:1] + "00"
        
        if main_class in self.DDC_SYSTEM:
            class_info = self.DDC_SYSTEM[main_class]
            subdivision = ddc_code if ddc_code in class_info["subdivisions"] else main_class
            
            return {
                "main_class": main_class,
                "main_class_name": class_info["name"],
                "subdivision": subdivision,
                "subdivision_name": class_info["subdivisions"].get(subdivision, class_info["name"]),
                "hierarchy": [main_class, subdivision] if subdivision != main_class else [main_class]
            }
        
        return {
            "main_class": "000",
            "main_class_name": "Computer science, information, and general works",
            "subdivision": "000",
            "subdivision_name": "Computer science, knowledge, and general works",
            "hierarchy": ["000"]
        }


class ContentClassifier:
    """Enhanced content classifier using AI and library standards."""
    
    def __init__(self):
        """Initialize content classifier with DDC support."""
        self.openai_client = None
        self.openrouter_api_key = None
        self.dewey_classifier = DeweyDecimalClassifier()
        
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
        """Enhanced keyword-based classification using comprehensive DDC system."""
        # Use the Dewey Decimal classifier for keyword-based classification
        ddc_code, confidence = self.dewey_classifier.classify_by_keywords(content)
        
        # Get detailed classification info
        class_info = self.dewey_classifier.get_classification_info(ddc_code)
        
        # Extract subjects from content for more context
        subjects = self._extract_subjects(content, ddc_code)
        
        return {
            'dewey_decimal': ddc_code,
            'dewey_info': class_info,
            'subjects': subjects,
            'confidence': confidence,
            'classification_method': 'enhanced_keyword_matching'
        }
    
    def _extract_subjects(self, content: str, ddc_code: str) -> List[str]:
        """Extract relevant subject keywords based on DDC classification."""
        content_lower = content.lower()
        subjects = []
        
        # Get keywords for the specific DDC code
        if ddc_code in self.dewey_classifier.KEYWORD_PATTERNS:
            keywords = self.dewey_classifier.KEYWORD_PATTERNS[ddc_code]
            subjects = [kw for kw in keywords if kw in content_lower]
        
        # Add general subjects from main class if no specific ones found
        if not subjects:
            main_class = ddc_code[:1] + "00"
            if main_class in self.dewey_classifier.KEYWORD_PATTERNS:
                keywords = self.dewey_classifier.KEYWORD_PATTERNS[main_class]
                subjects = [kw for kw in keywords if kw in content_lower]
        
        # Fallback to class name if no keywords found
        if not subjects:
            class_info = self.dewey_classifier.get_classification_info(ddc_code)
            subjects = [class_info["subdivision_name"].lower()]
        
        return subjects[:5]  # Limit to 5 subjects
    
    async def classify_with_confidence_threshold(
        self, 
        content: str, 
        min_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """Classify content with confidence threshold for manual review."""
        classification = await self.classify_content(content)
        
        if classification['confidence'] < min_confidence:
            classification['requires_review'] = True
            classification['review_reason'] = f"Low confidence ({classification['confidence']:.2f} < {min_confidence})"
        else:
            classification['requires_review'] = False
        
        return classification
    
    def get_all_dewey_classes(self) -> Dict[str, Any]:
        """Get all available Dewey Decimal main classes."""
        return {
            code: {
                "name": info["name"],
                "subdivisions": list(info["subdivisions"].keys())
            }
            for code, info in self.dewey_classifier.DDC_SYSTEM.items()
        }