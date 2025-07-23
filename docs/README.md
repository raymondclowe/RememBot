# RememBot Documentation

## Core Documents

### [RememBot Specification](../RememBot_specification.md)
Complete technical specification for the RememBot system including architecture, components, and implementation details.

### [Development Roadmap](../roadmap.md)
Phased development plan with incremental milestones, success criteria, and implementation timeline.

## Component Specifications

### [Background Parser Specification](background_parser_spec.md)
Detailed specification for the continuous content processing service that enhances stored items with AI-powered summaries, classifications, and metadata.

### [Background Knowledge Linker Specification](knowledge_linker_spec.md)
Future service specification for building knowledge graphs, detecting content relationships, and providing temporal-aware insights.

## Quick Reference

### System Architecture
- **Telegram Bot:** Simple interface for content ingestion and web access
- **Background Parser:** Continuous AI-powered content processing
- **Web Interface:** Rich content management and discovery
- **Background Knowledge Linker:** Advanced relationship detection and insights (future)

### Current Implementation Status
- ✅ **Phase 1 Complete:** Basic storage system with Telegram bot
- 🚧 **Phase 2 In Progress:** Simplified bot + web authentication
- 📋 **Phase 3 Planned:** Background content parser with AI
- 📋 **Future Phases:** Knowledge linking, analytics, advanced features

### Key Features
- **Privacy-First:** All data stored locally on user's system
- **Cloud AI Integration:** Leverages OpenRouter/OpenAI for processing
- **Local Fallback:** Optional Ollama support for privacy-sensitive content
- **Incremental Development:** Always-functional system with increasing capabilities
- **Multi-format Support:** Text, URLs, images, documents, and more

## Getting Started

1. **Installation:** Follow setup instructions in main README.md
2. **Configuration:** Set up API keys and preferences
3. **Telegram Bot:** Start sharing content with the bot
4. **Web Interface:** Use `/web` command to access management interface
5. **Background Processing:** Enable AI enhancement services

## API Documentation

### Database Schema
- **content_items:** Main storage table for all user content
- **web_tokens:** Authentication tokens for web interface access
- **user_activity:** Analytics and usage tracking
- **Processing tables:** Background parser queue and status

### Configuration Options
- **AI Services:** API keys, model preferences, cost controls
- **Processing:** Polling intervals, batch sizes, retry limits
- **Storage:** File paths, size limits, retention policies
- **Security:** Token expiry, encryption options

## Contributing

This is a personal knowledge management system designed for individual use. The architecture supports:

- **Extensible Content Processors:** Add support for new file types
- **Pluggable AI Services:** Integrate additional AI providers
- **Custom Classifications:** Extend taxonomy and tagging systems
- **Enhanced Visualizations:** Improve web interface capabilities

## Support and Troubleshooting

### Common Issues
- **API Rate Limits:** Configure delays and retry mechanisms
- **Storage Space:** Implement archival and cleanup policies
- **Processing Failures:** Check logs and retry failed items
- **Performance:** Optimize database queries and caching

### Monitoring
- **Health Checks:** Service availability and responsiveness
- **Processing Metrics:** Success rates, processing times, error rates
- **Cost Tracking:** AI API usage and expenses
- **User Analytics:** Content patterns and system usage

---

*This documentation reflects the current architecture as of the Phase 2 implementation. Future phases will add additional capabilities while maintaining backward compatibility.*