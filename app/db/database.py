"""
app/db/database.py
Database connection layer with cross-loop-safe helpers.

CONCURRENCY RULE (do not violate in this or any later phase):
Vasuki will eventually run a voice-capture thread that spins up its own
short-lived asyncio event loop per command, alongside a persistent
FastAPI/uvicorn event loop running the server. An event-loop-bound lock
does not work correctly across two different loop lifetimes. We use
threading.Lock here specifically because it is loop-agnostic — the
correct choice whenever code may be called from both a background thread
and the async server simultaneously.
"""
import asyncio
import threading
from typing import Any, Optional

import sqlalchemy as sa
from databases import Database

from app.core.config import settings
from app.db.models import metadata

# -- Async client used by FastAPI routes -----------------------------------
database = Database(settings.SYSTEM_DB_ASYNC_URL)

# -- Sync engine used only for one-time schema creation ----------------------
_sync_engine = sa.create_engine(settings.SYSTEM_DB_URL)

# -- Cross-loop safety primitives --------------------------------------------
_db_lock = threading.Lock()
_server_loop: Optional[asyncio.AbstractEventLoop] = None


def set_server_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Call once from FastAPI startup so other threads can identify the
    persistent server loop if ever needed in a later phase."""
    global _server_loop
    _server_loop = loop


def create_all_tables() -> None:
    """Synchronous, one-time schema creation. Safe to call at startup."""
    metadata.create_all(_sync_engine)


async def connect() -> None:
    await database.connect()


async def disconnect() -> None:
    await database.disconnect()


async def safe_execute(query, values: Optional[dict] = None) -> Any:
    """Thread-safe wrapped execute — safe even when called from a thread
    running its own event loop, because the lock is threading.Lock."""
    with _db_lock:
        return await database.execute(query, values)


async def safe_fetch_all(query, values: Optional[dict] = None) -> list:
    with _db_lock:
        return await database.fetch_all(query, values)


async def safe_fetch_one(query, values: Optional[dict] = None):
    with _db_lock:
        return await database.fetch_one(query, values)
