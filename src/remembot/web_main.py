#!/usr/bin/env python3
"""
Entry point for RememBot web interface.
"""

import uvicorn
from remembot.web.app import app

def main():
    """Run the web interface."""
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info"
    )

if __name__ == "__main__":
    main()