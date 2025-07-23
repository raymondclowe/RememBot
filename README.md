# RememBot

## AI and Embeddings Note

RememBot does **not** use GPU, NVIDIA libraries, or local embeddings (e.g., sentence-transformers, torch). All AI features are handled via cloud APIs (OpenAI, OpenRouter, etc). Optionally, you may use local models like Ollama or llamacpp for background tasks, but this is not required and not enabled by default.
Remember Bot - Back up your Brain

RememBot is a Telegram bot service that runs on Linux and helps you store, organize, and retrieve any content you share with it. Instead of bookmarking or saving content across different platforms, just share it with RememBot through Telegram and query it later using natural language.

## Features

- **Universal Content Ingestion**: Share URLs, images, documents (PDF, Word, Excel), and text
- **AI-Powered Organization**: Automatic classification using library science standards (Dewey Decimal)
- **Intelligent Search**: Natural language queries with AI-enhanced search capabilities
- **Silent Operation**: No chat clutter - content is stored silently for later retrieval
- **Privacy-Focused**: All data stored locally on your own server
- **Multi-User Support**: Segregated data storage per Telegram user

## Quick Start

### Prerequisites

- Linux server (Ubuntu/Debian recommended)
- Python 3.8+
- UV package manager (installed automatically)
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))

### Installation

1. Clone the repository:
```bash
git clone https://github.com/raymondclowe/RememBot.git
cd RememBot
```

2. Run the installation script:
```bash
sudo ./install.sh
```

3. Configure your bot token:
```bash
sudo systemctl edit remembot
```
Add your configuration:
```ini
[Service]
Environment=TELEGRAM_BOT_TOKEN=your_actual_bot_token
Environment=OPENAI_API_KEY=your_openai_key_optional
```

4. Start the service:
```bash
sudo systemctl enable remembot
sudo systemctl start remembot
```

5. Check status:
```bash
sudo systemctl status remembot
sudo journalctl -u remembot -f
```

### Development Setup

For development or manual running:

1. Install UV:
```bash
pip install uv
```

2. Install dependencies:
```bash
uv sync
```

3. Set environment variables:
```bash
export TELEGRAM_BOT_TOKEN=your_bot_token
export OPENAI_API_KEY=your_openai_key  # Optional
```

4. Run the bot:
```bash
uv run remembot
```

## Usage

1. **Start the bot**: Send `/start` to your bot on Telegram
2. **Share content**: Use Telegram's share feature or send directly:
   - URLs (articles, videos, tweets)
   - Images (with OCR text extraction)
   - Documents (PDF, Word, Excel)
   - Plain text notes
3. **Search later**: Use `/search <query>` to find your content
4. **View stats**: Use `/stats` to see your storage statistics

## Architecture

- **Long Polling**: Uses Telegram's long polling API (no webhook setup needed)
- **SQLite Database**: Local storage with user isolation
- **Content Processing**: Automatic text extraction from URLs, images (OCR), and documents
- **AI Classification**: Optional OpenAI integration for intelligent categorization
- **Systemd Service**: Runs as a background service with automatic restart

## Configuration

Configuration is handled through environment variables:

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token (required)
- `OPENAI_API_KEY`: OpenAI API key for AI features (optional)
- `REMEMBOT_DB_PATH`: Database file path (optional, defaults to ~/.remembot/remembot.db)
- `LOG_LEVEL`: Logging level (optional, defaults to INFO)

## Security

The systemd service runs with restricted permissions:
- Dedicated `remembot` user
- No new privileges
- Protected system access
- Private temporary directory
- Limited file system access

## Dependencies

Core dependencies are managed automatically:
- `python-telegram-bot`: Telegram API client
- `requests`: HTTP requests
- `beautifulsoup4`: Web scraping
- `Pillow`: Image processing
- `pytesseract`: OCR functionality
- `python-docx`: Word document parsing
- `PyPDF2`: PDF parsing
- `openpyxl`: Excel parsing
- `openai`: AI features (optional)
- `aiosqlite`: Async SQLite access

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

For issues, feature requests, or questions, please open an issue on GitHub.
