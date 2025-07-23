# GitHub Copilot Instructions

To ensure code suggestions use the most up-to-date documentation and best practices, always leverage web browsing, fetch, and/or Tavily MCP search capabilities. Before providing code or explanations, search for the latest official documentation, changelogs, or announcements relevant to the technology or API in question. Reference the most current sources in your suggestions whenever possible.

Copilot Agent environment has access to keys for testing:
- OPENROUTER_API_KEY
- TELEGRAM_BOT_TOKEN

Don't use 'python3' directly, always use `uv run` such as `uv run remembot` or `uv run filename.py`, and for dependancies don't use pip, us `uv add` such as `uv add package_name`.