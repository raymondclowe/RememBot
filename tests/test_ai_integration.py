"""
Test harness for AI API integration including OpenRouter support.
This test validates access to AI services for content classification and query processing.
"""

import pytest
import os
import asyncio
import aiohttp
import json
from unittest.mock import patch, AsyncMock

from remembot.classifier import ContentClassifier


class TestOpenRouterIntegration:
    """Test OpenRouter API integration."""
    
    def test_openrouter_api_key_availability(self):
        """Test if OpenRouter API key is available in environment."""
        api_key = os.getenv('OPENROUTER_API_KEY')
        
        if api_key:
            print(f"✓ OPENROUTER_API_KEY found (length: {len(api_key)})")
            assert api_key.startswith('sk-'), f"OpenRouter API key should start with 'sk-', got: {api_key[:10]}..."
            assert len(api_key) > 20, f"OpenRouter API key seems too short: {len(api_key)} characters"
        else:
            print("✗ OPENROUTER_API_KEY not found in environment")
            pytest.skip("OPENROUTER_API_KEY not available - this is expected in dev environments")
    
    @pytest.mark.asyncio
    async def test_openrouter_api_connection(self):
        """Test actual connection to OpenRouter API."""
        api_key = os.getenv('OPENROUTER_API_KEY')
        
        if not api_key:
            pytest.skip("OPENROUTER_API_KEY not available")
        
        # Test with a simple API call
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://github.com/raymondclowe/RememBot',
            'X-Title': 'RememBot Test'
        }
        
        test_payload = {
            'model': 'openai/gpt-3.5-turbo',
            'messages': [
                {'role': 'user', 'content': 'Respond with just the word "test" to confirm API access.'}
            ],
            'max_tokens': 10
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    'https://openrouter.ai/api/v1/chat/completions',
                    headers=headers,
                    json=test_payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    print(f"OpenRouter API Response Status: {response.status}")
                    response_text = await response.text()
                    print(f"Response: {response_text[:200]}...")
                    
                    if response.status == 200:
                        data = await response.json()
                        assert 'choices' in data
                        assert len(data['choices']) > 0
                        print("✓ OpenRouter API connection successful")
                    elif response.status == 401:
                        pytest.fail("OpenRouter API key is invalid or expired")
                    elif response.status == 429:
                        pytest.fail("OpenRouter API rate limit exceeded")
                    else:
                        pytest.fail(f"OpenRouter API error: {response.status} - {response_text}")
                        
            except asyncio.TimeoutError:
                pytest.fail("OpenRouter API request timed out")
            except Exception as e:
                pytest.fail(f"OpenRouter API connection failed: {e}")
    
    @pytest.mark.asyncio
    async def test_openrouter_classification(self):
        """Test content classification using OpenRouter."""
        api_key = os.getenv('OPENROUTER_API_KEY')
        
        if not api_key:
            pytest.skip("OPENROUTER_API_KEY not available")
        
        # Create a classifier that uses OpenRouter
        classifier = OpenRouterClassifier()
        
        test_content = "This is an article about Python programming and machine learning algorithms."
        
        result = await classifier.classify_content(test_content)
        
        assert 'dewey_decimal' in result
        assert 'subjects' in result
        assert 'confidence' in result
        assert result['classification_method'] == 'openrouter_ai'
        
        # Should classify as computer science (004 or 005)
        assert result['dewey_decimal'] in ["004", "005"], f"Expected 004 or 005, got {result['dewey_decimal']}"
        assert len(result['subjects']) > 0
        assert result['confidence'] > 0.5


class OpenRouterClassifier(ContentClassifier):
    """Enhanced classifier that supports OpenRouter API."""
    
    def __init__(self):
        """Initialize with OpenRouter support."""
        super().__init__()
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        
    async def classify_content(self, content: str):
        """Classify content using OpenRouter if available, fallback to OpenAI or simple classification."""
        if not content or not content.strip():
            return {
                'dewey_decimal': None,
                'subjects': [],
                'confidence': 0.0,
                'classification_method': 'none'
            }
        
        # Try OpenRouter first if available
        if self.openrouter_api_key:
            try:
                return await self._openrouter_classify(content)
            except Exception as e:
                print(f"OpenRouter classification failed, falling back: {e}")
        
        # Fallback to existing implementation
        return await super().classify_content(content)
    
    async def _openrouter_classify(self, content: str):
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
                    # Fallback to simple classification
                    return self._simple_classify(content)


class TestAIKeyConfiguration:
    """Test different ways to configure AI API keys."""
    
    def test_environment_variable_detection(self):
        """Test detection of AI API keys in environment."""
        keys_to_check = [
            'OPENROUTER_API_KEY',
            'OPENAI_API_KEY'
        ]
        
        found_keys = []
        for key in keys_to_check:
            value = os.getenv(key)
            if value:
                found_keys.append(key)
                print(f"✓ {key} found (length: {len(value)})")
            else:
                print(f"✗ {key} not found")
        
        print(f"\nFound {len(found_keys)} AI API key(s): {found_keys}")
        
        # At least one should be available for AI features to work
        if not found_keys:
            print("\n⚠️  No AI API keys found. AI classification will use fallback methods.")
    
    def test_github_secrets_guidance(self):
        """Provide guidance on GitHub secrets configuration."""
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        
        if not openrouter_key:
            print("\n" + "="*60)
            print("OPENROUTER_API_KEY CONFIGURATION GUIDANCE")
            print("="*60)
            print("\nTo provide the OpenRouter API key to your dev environment:")
            print("\n1. GitHub Codespaces/Actions (Recommended):")
            print("   - Go to repository Settings > Secrets and variables > Actions")
            print("   - Add OPENROUTER_API_KEY as a repository secret")
            print("   - The secret will be available in the environment automatically")
            print("\n2. Local Development:")
            print("   - Create a .env file in the project root")
            print("   - Add: OPENROUTER_API_KEY=sk-your-key-here")
            print("   - Make sure .env is in .gitignore (already configured)")
            print("\n3. Testing in CI/CD:")
            print("   - Use GitHub Actions secrets")
            print("   - Access via ${{ secrets.OPENROUTER_API_KEY }}")
            print("\n4. Docker/Container Deployment:")
            print("   - Pass as environment variable: -e OPENROUTER_API_KEY=sk-...")
            print("   - Use Docker secrets for production")
            print("\n5. Systemd Service (Production):")
            print("   - Use systemd environment files")
            print("   - Configure in /etc/remembot/environment")
            print("="*60)
    
    @pytest.mark.asyncio
    async def test_fallback_behavior(self):
        """Test that the system works without AI API keys."""
        # Temporarily remove API keys
        with patch.dict(os.environ, {}, clear=True):
            classifier = ContentClassifier()
            
            result = await classifier.classify_content("Python programming tutorial")
            
            # Should still work with keyword-based classification
            assert result['dewey_decimal'] == "004"
            assert 'programming' in result['subjects']
            assert result['classification_method'] == 'keyword_matching'
            print("✓ Fallback classification working correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])