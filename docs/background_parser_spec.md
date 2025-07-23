# Background Parser Specification

## Overview

The Background Parser is a separate service that continuously processes stored content items using AI to enhance them with summaries, key points, and classifications. This service runs independently from the Telegram bot to ensure content processing doesn't block user interactions.

## Architecture

### Service Type
- **systemd service** running as a daemon
- **Independent process** from the Telegram bot
- **Continuous operation** with configurable polling intervals
- **Resilient design** with error recovery and retry mechanisms

### Processing Flow

1. **Database Polling**
   - Continuously scan database for items with `parse_status = 'pending'`
   - Process items in chronological order (oldest first)
   - Handle multiple content types with appropriate processors

2. **Content Type Handlers**

#### Text Processing
- **Input:** Plain text messages and notes
- **Processing:** 
  - Basic metadata extraction (word count, language detection)
  - AI summarization using OpenRouter/OpenAI
  - Content classification using library standards
- **Output:** Summary, classification tags, confidence scores

#### URL Processing  
- **Input:** Web page URLs
- **Processing:**
  - HTTP content fetching with user-agent rotation
  - HTML parsing and text extraction to markdown
  - Fallback to Tavily MCP Extract for captcha/blocked sites
  - AI summary and key point extraction
  - Source platform detection and metadata
- **Output:** Clean text content, summary, key points, metadata

#### Image Processing
- **Input:** Image files (JPEG, PNG, etc.)
- **Processing:**
  - EXIF metadata extraction (camera, location, timestamp)
  - Local OCR using Tesseract for text extraction
  - AI image description using vision models
  - Smart fallback to cloud AI for unclear OCR results
  - Text content classification if OCR successful
- **Output:** Image description, extracted text, metadata

#### Document Processing
- **Input:** PDF, Word, Excel, PowerPoint files
- **Processing:**
  - Format-specific parsing (PyPDF2, python-docx, openpyxl)
  - Text extraction with structure preservation
  - AI summarization with document type context
  - Multiple format output for spreadsheets (CSV conversion)
- **Output:** Extracted text, formatted summary, document metadata

#### Other Document Types
- **Input:** Any binary files not covered above
- **Processing:**
  - Best-effort text extraction from binary content
  - AI summarization of extracted readable content
  - File type and format detection
- **Output:** Extracted text, summary, file metadata

### AI Integration Strategy

#### Cloud AI Services (Primary)
- **OpenRouter API** for variety and cost-effectiveness
- **OpenAI API** for reliability and advanced capabilities
- **Model Selection Logic:**
  - Simple tasks: Cheaper models (GPT-3.5, Claude Instant)
  - Complex tasks: Advanced models (GPT-4, Claude-3)
  - Image analysis: Vision-capable models
  - Cost vs. capability balancing

#### Local AI Services (Optional)
- **Ollama integration** for privacy-sensitive content
- **Model Capability Assessment:**
  - Automatic quality checking of local model outputs
  - Fallback to cloud AI for subpar results
  - User-configurable privacy vs. capability trade-offs

#### Processing Logic
```python
async def process_content(item):
    # Attempt local processing first (if enabled)
    if config.prefer_local_ai:
        try:
            result = await local_ai_processor.process(item)
            if quality_check(result):
                return result
        except Exception:
            pass
    
    # Fallback to cloud AI
    return await cloud_ai_processor.process(item)
```

### Storage Strategy

#### Original Content Preservation
- **Database Storage:** Small items (< 1MB) stored as BLOB
- **Filesystem Storage:** Large items stored with git-like hashing
  - Directory structure: `files/ab/cd/abcd1234...` (first 4 chars as path)
  - SHA-256 hashing for deduplication
  - Consider using actual git repository for version control

#### Web Page Snapshots
- **Complete HTML Storage:** Preserve original page appearance
- **Timestamp Snapshots:** Multiple versions for changing content
- **Archive Integration:** Link to Internet Archive when available

#### Processing Results
- **Structured Storage:** JSON metadata with AI results
- **Version Tracking:** Processing version for result upgrades
- **Confidence Scores:** AI processing quality indicators

### Error Handling and Resilience

#### Retry Mechanisms
- **Exponential Backoff:** 1s, 2s, 4s, 8s, 16s delays
- **Maximum Retries:** 5 attempts before marking as failed
- **Different Error Types:**
  - Network errors: Full retry cycle
  - API rate limits: Longer delays
  - Content format errors: Mark as failed immediately

#### Failure Recovery
- **Graceful Degradation:** Store content even if processing fails
- **Error Logging:** Detailed logs for debugging
- **Manual Retry:** Admin interface for failed item reprocessing
- **Health Monitoring:** Service status and processing metrics

### Configuration

#### Processing Settings
```yaml
background_parser:
  poll_interval: 5  # seconds between database checks
  batch_size: 10    # items to process in each batch
  max_retries: 5    # maximum retry attempts
  timeout: 300      # processing timeout in seconds
  
ai_services:
  prefer_local: false           # try local AI first
  openrouter_api_key: "${OPENROUTER_API_KEY}"
  openai_api_key: "${OPENAI_API_KEY}"
  
models:
  text_summary: "anthropic/claude-3-haiku"
  image_analysis: "openai/gpt-4-vision-preview"
  classification: "openai/gpt-3.5-turbo"
```

### Performance Considerations

#### Scalability
- **Parallel Processing:** Multiple worker threads for different content types
- **Queue Management:** Priority queues for different content types
- **Resource Limits:** CPU and memory usage controls
- **Rate Limiting:** Respect AI service rate limits

#### Monitoring
- **Processing Metrics:** Items per hour, success rates, error rates
- **Performance Tracking:** Average processing time by content type
- **Health Checks:** Service availability and responsiveness
- **Cost Tracking:** AI API usage and costs

### Database Schema Changes

```sql
-- Add processing status tracking
ALTER TABLE content_items ADD COLUMN parse_status TEXT DEFAULT 'pending';
ALTER TABLE content_items ADD COLUMN parse_attempts INTEGER DEFAULT 0;
ALTER TABLE content_items ADD COLUMN parse_error TEXT NULL;
ALTER TABLE content_items ADD COLUMN ai_summary TEXT NULL;
ALTER TABLE content_items ADD COLUMN ai_key_points TEXT NULL;
ALTER TABLE content_items ADD COLUMN processing_version INTEGER DEFAULT 1;

-- Add processing queue table
CREATE TABLE processing_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id INTEGER NOT NULL,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_started_at TIMESTAMP NULL,
    FOREIGN KEY (content_item_id) REFERENCES content_items (id)
);
```

### Service Management

#### systemd Service
```ini
[Unit]
Description=RememBot Background Parser
After=network.target remembot-bot.service
Requires=remembot-bot.service

[Service]
Type=simple
User=remembot
WorkingDirectory=/opt/remembot
ExecStart=/opt/remembot/.venv/bin/python -m remembot.background_parser
Restart=always
RestartSec=10
Environment=PYTHONPATH=/opt/remembot

[Install]
WantedBy=multi-user.target
```

#### Process Management
- **Graceful Shutdown:** Complete current processing before exit
- **Signal Handling:** SIGTERM for clean shutdown, SIGUSR1 for config reload
- **Logging:** Structured logging to syslog and files
- **Health Endpoint:** HTTP endpoint for monitoring

This background parser design ensures that content processing is robust, scalable, and doesn't interfere with the user experience while providing rich AI-enhanced metadata for all stored content.