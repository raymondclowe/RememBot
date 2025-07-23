# OpenRouter Integration Guide

RememBot has been successfully pivoted to use OpenRouter as the primary AI service provider, with OpenAI as a fallback option. This provides:

## Benefits of OpenRouter

- **Wider Model Selection**: Access to hundreds of AI models from different providers
- **Cost Effectiveness**: More competitive pricing and flexible model options
- **No Geoblocking**: Avoids geographical restrictions that affect some AI services
- **Unified API**: Single endpoint for multiple AI providers

## Configuration

### Environment Variables (Priority Order)

1. **Primary**: `OPENROUTER_API_KEY` - Used for all AI operations when available
2. **Fallback**: `OPENAI_API_KEY` - Used when OpenRouter is not available

### Example Configuration

```bash
# Primary AI service
export OPENROUTER_API_KEY=sk-or-v1-your-openrouter-key

# Optional fallback
export OPENAI_API_KEY=sk-your-openai-key
```

## Implementation Details

### Using OpenAI SDK with OpenRouter

The implementation follows OpenRouter's recommended approach using the OpenAI SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="<OPENROUTER_API_KEY>",
)

completion = client.chat.completions.create(
    extra_headers={
        "HTTP-Referer": "https://github.com/raymondclowe/RememBot",
        "X-Title": "RememBot",
    },
    model="openai/gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Your message"}]
)
```

### API Priority Logic

1. **OpenRouter First**: All AI components (classifier, query_handler) try OpenRouter first
2. **Graceful Fallback**: If OpenRouter fails, system falls back to OpenAI
3. **Keyword Fallback**: If no AI services available, uses enhanced keyword classification

### Affected Components

- **Content Classifier**: Uses OpenRouter for Dewey Decimal classification
- **Query Handler**: Uses OpenRouter for enhanced search and result summarization
- **Health Checks**: Monitors OpenRouter API connectivity
- **Configuration**: Prioritizes OpenRouter in all settings

## Backward Compatibility

- Existing OpenAI integrations continue to work
- Configuration files don't need updates
- Systems without OpenRouter keys fall back gracefully
- All existing tests pass

## Verification

Run the API key checker to verify your setup:

```bash
uv run python check_api_keys.py
```

Expected output with OpenRouter:
```
🎉 Ready for AI-powered classification!
✅ OPENROUTER_API_KEY found!
```

## Cost and Usage

OpenRouter provides detailed usage tracking and cost management. Models are selected based on:

- **Simple tasks**: More cost-effective models (gpt-3.5-turbo)
- **Complex analysis**: Advanced models when needed
- **Automatic failover**: Between providers for reliability

## Getting OpenRouter API Key

1. Visit [OpenRouter.ai](https://openrouter.ai)
2. Sign up for an account
3. Navigate to API Keys section
4. Generate a new API key (starts with `sk-or-`)
5. Add to your environment variables

## Support

The OpenRouter integration maintains the same interface as the previous OpenAI integration, ensuring seamless operation while providing enhanced capabilities and better cost management.