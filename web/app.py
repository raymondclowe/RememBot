"""
Basic FastAPI web frontend for RememBot user authentication and data viewing.
"""

import random
import time
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# In-memory store for demo (replace with DB in production)
# pin_store: {pin: {"session_id": ..., "created": ..., "telegram_user_id": ...}}
pin_store = {}
PIN_EXPIRY_SECONDS = 1800  # 30 minutes

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session = request.session
    telegram_user_id = session.get("telegram_user_id")
    if telegram_user_id:
        # Show table of saved info (stub)
        # TODO: Query DB for user's saved info
        data = [
            {"id": 1, "type": "url", "content": "https://example.com", "created_at": "2025-07-22"},
            {"id": 2, "type": "text", "content": "Some note", "created_at": "2025-07-21"},
        ]
        return templates.TemplateResponse("table.html", {"request": request, "data": data, "telegram_user_id": telegram_user_id})
    else:
        return templates.TemplateResponse("auth.html", {"request": request})

@app.post("/generate_pin", response_class=HTMLResponse)
async def generate_pin(request: Request):
    pin = str(random.randint(1000, 9999))
    session = request.session
    session["pin"] = pin
    pin_store[pin] = {"session_id": id(session), "created": time.time(), "telegram_user_id": None}
    return templates.TemplateResponse("enter_pin.html", {"request": request, "pin": pin})

@app.post("/submit_pin", response_class=HTMLResponse)
async def submit_pin(request: Request, pin: str = Form(...)):
    session = request.session
    expected_pin = session.get("pin")
    if not expected_pin or pin != expected_pin:
        return templates.TemplateResponse("enter_pin.html", {"request": request, "pin": expected_pin, "error": "Incorrect PIN. Try again."})
    # Check if PIN is valid and not expired
    pin_info = pin_store.get(pin)
    if not pin_info or (time.time() - pin_info["created"] > PIN_EXPIRY_SECONDS):
        return templates.TemplateResponse("enter_pin.html", {"request": request, "pin": expected_pin, "error": "PIN expired. Please generate a new one."})
    # Check if Telegram user ID has been set by bot
    telegram_user_id = pin_info.get("telegram_user_id")
    if not telegram_user_id:
        return templates.TemplateResponse("enter_pin.html", {"request": request, "pin": expected_pin, "error": "PIN not yet sent to bot. Please send the PIN to RememBot on Telegram."})
    # Save telegram user id in session
    session["telegram_user_id"] = telegram_user_id
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    session = request.session
    session.clear()
    return RedirectResponse("/", status_code=302)

# API endpoint for bot to link PIN to Telegram user ID
@app.post("/api/link_pin")
async def link_pin(pin: str = Form(...), telegram_user_id: str = Form(...)):
    pin_info = pin_store.get(pin)
    if not pin_info or (time.time() - pin_info["created"] > PIN_EXPIRY_SECONDS):
        raise HTTPException(status_code=400, detail="PIN expired or invalid")
    pin_info["telegram_user_id"] = telegram_user_id
    return {"status": "linked"}
