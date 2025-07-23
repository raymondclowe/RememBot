# Specification for "RememBot" - short for remember robot.

## AI and Embeddings Approach

RememBot does not use GPU acceleration, NVIDIA libraries, or local embedding models. All semantic search and AI features are performed via cloud APIs (OpenAI, OpenRouter, etc). Optionally, local models (Ollama, llamacpp) may be supported for background tasks, but are not required or enabled by default.

It will be a telegram bot that runs as a service on a linux desktop - it is behind a nat firewall so it may need to do long polling not webhook.

## RememBot Specification

### Overview

**RememBot** (Remember Robot) is a personal knowledge management system consisting of three main components:

1. **Telegram Bot** - Simple interface for content ingestion and web access
2. **Background Parser** - Continuous AI-powered content processing  
3. **Web Interface** - Rich viewing and management interface

The system runs on a Linux desktop behind a NAT firewall, using **long polling** for Telegram communication. It enables users to share any content (URLs, images, documents, text) through Telegram's "Share" feature, which is then intelligently processed and made available through a web interface.

### Architecture & Components

#### 1. Telegram Bot
**Purpose:** Minimal interface focused on content ingestion and web access

**Functionality:**
- **Silent Content Processing:** Receives and stores any shared content (text, URLs, images, voice notes, PDFs, documents) without replies or acknowledgment messages
- **Help Command:** `/help` - Provides overview of how the system works and how to use it
- **Web Access Command:** `/web` - Generates a secure link with authentication parameters for accessing the web interface

**Important:** The bot does NOT provide search, statistics, or content management commands. All content interaction happens through the web interface.

#### 2. Background Parser
**Purpose:** Continuous processing of stored items with AI enhancement

**Process:**
- Continuously monitors the database for unparsed items
- Processes different content types with appropriate handlers:
  - **Text:** Store with metadata, generate AI summary
  - **URLs:** Fetch page content, extract text as markdown, generate AI summary and key points, enable full-text search
  - **Images:** Extract EXIF metadata, generate AI description of content, perform OCR for text extraction, use enhanced AI if OCR results are unclear
  - **PDFs:** Extract text content, generate AI summary
  - **Office Documents:** Parse to text-based formats (CSV for spreadsheets), send to AI with context for summarization
  - **Other Documents:** Extract readable text from binary content, generate AI summary

**Storage Strategy:**
- **Original Content:** Always preserved
  - Small items: Stored in database
  - Large items: Stored in filesystem with git-like hashing for organization
  - Web pages: Store complete HTML snapshot for historical reference
- **Processed Content:** AI summaries, extracted text, metadata stored alongside originals

#### 3. Background Knowledge Linker
**Purpose:** Build connections and knowledge graphs (future component)

**Concept:**
- Continuously analyze all knowledge items for connections
- Build metadata database of topics linking to individual items
- Create temporal-aware knowledge graph
- Enable topic-based discovery and cross-referencing

#### 4. Web Interface
**Purpose:** Primary user interface for content management and discovery

**Authentication:** 
- Accessed via secure link from `/web` command containing:
  - Secret authentication token
  - Telegram user ID parameter
  - Automatic login without additional credentials

**Features:**
- **Simple Table View:** Recent items first with pagination
- **Full-Text Search:** Includes original content and AI-generated summaries
- **Content Management:** Delete, edit, and organize items
- **Responsive Design:** Works on mobile and desktop

### Technical Architecture

| Component | Technology / Tool |
| :-- | :-- |
| Telegram Bot | Python/python-telegram-bot with long polling |
| Background Parser | Python service with continuous processing |
| Content Processing | Custom fetch + Tavily MCP Extract fallback |
| AI Processing | OpenAI/OpenRouter APIs for summaries and classification |
| Image Processing | Local OCR (Tesseract) + AI vision models |
| Document Parsing | python-docx, PyPDF2, openpyxl |
| Database | SQLite (local, upgradeable to PostgreSQL) |
| Web Interface | Modern web framework (Flask/FastAPI + React/Vue) |
| File Storage | Git-like hashing system for large files |
| System Service | systemd units for all components |

### Database Schema

| Field | Description |
| :-- | :-- |
| `id` | Unique item ID |
| `user_telegram_id` | Telegram user ID (user isolation) |
| `original_share` | Raw input content |
| `content_type` | Type classification (url, image, document, text) |
| `metadata` | JSON: date, time, source platform, processing status |
| `extracted_info` | Processed text content |
| `ai_summary` | AI-generated summary |
| `ai_key_points` | AI-extracted key points |
| `taxonomy` | AI classification tags |
| `parse_status` | Processing status (pending, processing, complete, error) |
| `processing_time` | Time taken for processing |

### User Experience Flow

1. **Content Sharing:** User shares any content with RememBot via Telegram
2. **Silent Storage:** Bot stores content immediately without user feedback  
3. **Background Processing:** Parser processes content asynchronously with AI
4. **Web Access:** User uses `/web` command to get authenticated web interface link
5. **Content Discovery:** User searches, browses, and manages content through web interface

### Deployment & Infrastructure

- **Platform:** Linux desktop service (Ubuntu/Debian recommended)
- **Network:** NAT firewall compatibility with long polling
- **Services:** Multiple systemd services for bot, parser, knowledge linker, web interface
- **Package Management:** Python with UV for modern dependency management
- **Storage:** Local filesystem and database with cloud API integration

### Privacy & Security

- **Local Storage:** All data stored locally on user's machine
- **User Isolation:** Complete separation of data by Telegram user ID
- **Secure Web Access:** Time-limited authentication tokens
- **API Security:** Secure handling of cloud AI API keys

### Future Enhancements

- **Knowledge Graph Visualization:** Visual representation of content connections
- **Advanced Analytics:** Trends, patterns, and insights from stored content
- **Export Options:** Multiple format support for data portability
- **Collaborative Features:** Shared knowledge bases for teams
- **Mobile App:** Native mobile interface complementing web access

This architecture provides a clean separation of concerns with scalable, maintainable components while keeping the user experience simple and focused.