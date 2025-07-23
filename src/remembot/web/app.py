"""
FastAPI web frontend for RememBot with token-based authentication and real database integration.
"""

import asyncio
import json
import logging
import math
import os
from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

# Import RememBot database manager using proper relative imports
from ..database import DatabaseManager

# Setup logging
logger = logging.getLogger(__name__)

app = FastAPI()

# Load secret key from environment for security
session_secret_key = os.environ.get("SESSION_SECRET_KEY", "supersecretkey-change-in-production")
if session_secret_key == "supersecretkey-change-in-production" and os.environ.get("ENV") == "production":
    raise RuntimeError("SESSION_SECRET_KEY must be set in the environment for production.")
app.add_middleware(SessionMiddleware, secret_key=session_secret_key)
app.mount("/static", StaticFiles(directory="src/remembot/web/static"), name="static")
templates = Jinja2Templates(directory="src/remembot/web/templates")

# Initialize database manager with default path
database_path = os.environ.get('REMEMBOT_DATABASE_PATH', 'data/remembot.db')
db_manager = DatabaseManager(database_path)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int = Query(1, ge=1), search: str = Query(""), content_type: str = Query("")):
    """Main page - show user's content if authenticated, otherwise show login."""
    session = request.session
    telegram_user_id = session.get("telegram_user_id")
    
    if telegram_user_id:
        # Show table of real saved info
        items_per_page = 20
        offset = (page - 1) * items_per_page
        
        try:
            if search.strip():
                # Perform search
                results, total = await db_manager.search_content(
                    user_telegram_id=telegram_user_id,
                    query=search,
                    content_type=content_type if content_type else None,
                    limit=items_per_page,
                    offset=offset
                )
            else:
                # Get recent items (use search with empty query to leverage pagination)
                results, total = await db_manager.search_content(
                    user_telegram_id=telegram_user_id,
                    query="",
                    content_type=content_type if content_type else None,
                    limit=items_per_page,
                    offset=offset
                )
            
            # Process results for display
            processed_items = []
            for item in results:
                # Parse metadata for display
                metadata = {}
                if item.get('metadata'):
                    try:
                        metadata = json.loads(item['metadata'])
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Parse taxonomy for display
                taxonomy = {}
                if item.get('taxonomy'):
                    try:
                        taxonomy = json.loads(item['taxonomy'])
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Create display item
                display_item = {
                    'id': item['id'],
                    'content_type': item['content_type'],
                    'original_share': item['original_share'],
                    'extracted_info': item.get('extracted_info', ''),
                    'source_platform': item.get('source_platform', 'unknown'),
                    'created_at': item['created_at'],
                    'title': metadata.get('title', 'No title'),
                    'tags': taxonomy.get('categories', []) if isinstance(taxonomy.get('categories'), list) else []
                }
                
                # Truncate long content for table display
                if len(display_item['original_share']) > 100:
                    display_item['display_content'] = display_item['original_share'][:100] + "..."
                else:
                    display_item['display_content'] = display_item['original_share']
                
                processed_items.append(display_item)
            
            # Calculate pagination
            total_pages = math.ceil(total / items_per_page) if total > 0 else 1
            
            # Get user stats
            stats = await db_manager.get_user_stats(telegram_user_id)
            
            return templates.TemplateResponse("table.html", {
                "request": request, 
                "items": processed_items,
                "telegram_user_id": telegram_user_id,
                "current_page": page,
                "total_pages": total_pages,
                "total_items": total,
                "search_query": search,
                "content_type_filter": content_type,
                "stats": stats
            })
            
        except Exception as e:
            # Log error and show empty state
            logger.error(f"Error loading user content: {e}", exc_info=True)
            return templates.TemplateResponse("table.html", {
                "request": request,
                "items": [],
                "telegram_user_id": telegram_user_id,
                "current_page": 1,
                "total_pages": 1,
                "total_items": 0,
                "search_query": search,
                "content_type_filter": content_type,
                "error": "Failed to load content. Please try again later.",
                "stats": {}
            })
    else:
        return templates.TemplateResponse("auth.html", {"request": request})

@app.get("/auth", response_class=HTMLResponse)
async def auth_with_token(request: Request, token: str, user_id: int, expires: int):
    """Authenticate user with token from Telegram bot."""
    try:
        # Validate the token
        is_valid = await db_manager.validate_web_token(token, user_id)
        
        if is_valid:
            # Set session
            session = request.session
            session["telegram_user_id"] = user_id
            return RedirectResponse("/", status_code=302)
        else:
            return templates.TemplateResponse("auth.html", {
                "request": request, 
                "error": "Invalid or expired authentication token. Please request a new /web link from the bot."
            })
            
    except Exception as e:
        print(f"Authentication error: {e}")
        return templates.TemplateResponse("auth.html", {
            "request": request,
            "error": "Authentication failed. Please try again."
        })

@app.get("/item/{item_id}", response_class=HTMLResponse)
async def view_item(request: Request, item_id: int):
    """View individual item details."""
    session = request.session
    telegram_user_id = session.get("telegram_user_id")
    
    if not telegram_user_id:
        return RedirectResponse("/", status_code=302)
    
    try:
        item = await db_manager.get_content_by_id(telegram_user_id, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Parse metadata and taxonomy
        metadata = {}
        taxonomy = {}
        
        if item.get('metadata'):
            try:
                metadata = json.loads(item['metadata'])
            except (json.JSONDecodeError, TypeError):
                pass
        
        if item.get('taxonomy'):
            try:
                taxonomy = json.loads(item['taxonomy'])
            except (json.JSONDecodeError, TypeError):
                pass
        
        return templates.TemplateResponse("item_detail.html", {
            "request": request,
            "item": item,
            "metadata": metadata,
            "taxonomy": taxonomy,
            "telegram_user_id": telegram_user_id
        })
        
    except Exception as e:
        print(f"Error loading item {item_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load item")

@app.post("/delete/{item_id}")
async def delete_item(request: Request, item_id: int):
    """Delete an item."""
    session = request.session
    telegram_user_id = session.get("telegram_user_id")
    
    if not telegram_user_id:
        return RedirectResponse("/", status_code=302)
    
    try:
        deleted = await db_manager.delete_content(telegram_user_id, item_id)
        if deleted:
            return RedirectResponse("/", status_code=302)
        else:
            raise HTTPException(status_code=404, detail="Item not found")
            
    except Exception as e:
        print(f"Error deleting item {item_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete item")

@app.get("/logout")
async def logout(request: Request):
    """Log out user."""
    session = request.session
    session.clear()
    return RedirectResponse("/", status_code=302)

# Legacy PIN-based authentication endpoints (kept for backward compatibility)
@app.post("/generate_pin", response_class=HTMLResponse)
async def generate_pin(request: Request):
    """Legacy PIN generation - redirect to new auth."""
    return templates.TemplateResponse("auth.html", {
        "request": request, 
        "info": "Please use the /web command in your Telegram bot to get an authentication link."
    })

@app.post("/submit_pin", response_class=HTMLResponse)
async def submit_pin(request: Request, pin: str = Form(...)):
    """Legacy PIN submission - redirect to new auth."""
    return templates.TemplateResponse("auth.html", {
        "request": request,
        "info": "PIN authentication is deprecated. Please use the /web command in your Telegram bot."
    })

# API endpoint for bot to link PIN to Telegram user ID (legacy, kept for compatibility)
@app.post("/api/link_pin")
async def link_pin(pin: str = Form(...), telegram_user_id: str = Form(...)):
    """Legacy PIN linking endpoint."""
    return {"status": "deprecated", "message": "Use token-based authentication instead"}
