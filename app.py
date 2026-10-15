"""FastAPI application entrypoint for BuilderBot.

Assembles modular routers and static UI assets.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from routes import (
    builds_router,
    catalog_router,
    exports_router,
    sourcing_router,
    system_router,
)
from core.common.state import get_state
from core.intelligence.sourcing import find_sources
from routes.helpers import get_llm, get_tf

_runtime_keys = get_state().runtime_keys
_tf = get_tf
_llm = get_llm

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="BuilderBot API",
    version="2.0.0",
    description="Robot component selection, compatibility validation, and engineering reports.",
)

# Static web interface
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Modular domain routers
app.include_router(system_router)
app.include_router(builds_router)
app.include_router(catalog_router)
app.include_router(sourcing_router)
app.include_router(exports_router)


@app.get("/", response_class=HTMLResponse)
def home():
    """Serves the main single-page web application."""
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.exception_handler(Exception)
async def unhandled_error(request, exc):
    """Log server-side exception details and return clean error response."""
    logging.getLogger("builderbot").exception("Unhandled application error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Unexpected server error. Check the application logs."},
    )
