#!/usr/bin/env python3
"""
Quick script to check for OpenRouter API key availability.
This can be run to verify the GitHub secret is properly configured.
"""

import os
import sys

def check_openrouter_key():
    """Check if OpenRouter API key is available."""
    print("🔍 Checking for OPENROUTER_API_KEY...")
    
    api_key = os.getenv('OPENROUTER_API_KEY')
    
    if api_key:
        print(f"✅ OPENROUTER_API_KEY found!")
        print(f"   Length: {len(api_key)} characters")
        print(f"   Prefix: {api_key[:10]}...")
        
        # Basic validation
        if api_key.startswith('sk-'):
            print("✅ API key format looks correct (starts with 'sk-')")
        else:
            print("⚠️  API key doesn't start with 'sk-' - this might be incorrect")
        
        if len(api_key) > 20:
            print("✅ API key length seems reasonable")
        else:
            print("⚠️  API key seems short - might be a test key")
            
        return True
    else:
        print("❌ OPENROUTER_API_KEY not found in environment")
        print("\n💡 To add the API key:")
        print("   1. For GitHub Codespaces: Repository → Settings → Secrets → Add OPENROUTER_API_KEY")
        print("   2. For local dev: Add OPENROUTER_API_KEY=sk-... to .env file")
        print("   3. For testing: export OPENROUTER_API_KEY=sk-...")
        
        return False

def check_other_keys():
    """Check for other AI API keys."""
    print("\n🔍 Checking for other AI API keys...")
    
    keys_found = []
    
    # Check OpenAI
    if os.getenv('OPENAI_API_KEY'):
        keys_found.append('OPENAI_API_KEY')
        print("✅ OPENAI_API_KEY found")
    
    if keys_found:
        print(f"\n🎯 Found {len(keys_found)} alternative AI API key(s): {', '.join(keys_found)}")
        print("   These can be used as fallbacks for AI classification")
    else:
        print("ℹ️  No alternative AI API keys found")
        print("   System will use keyword-based classification as fallback")

if __name__ == "__main__":
    print("🤖 RememBot API Key Checker")
    print("=" * 40)
    
    openrouter_available = check_openrouter_key()
    check_other_keys()
    
    print("\n" + "=" * 40)
    if openrouter_available:
        print("🎉 Ready for AI-powered classification!")
    else:
        print("📝 Keyword-based classification will be used")
        print("   Add OPENROUTER_API_KEY to enable AI features")