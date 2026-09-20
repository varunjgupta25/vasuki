"""
app/main.py
Phase 0 entry point: settings + DB + a health check only.
No voice, no intent parsing, no execution yet — those arrive in later phases.
"""
import asyncio

from fastapi import FastAPI

from app.db.database import connect, disconnect, create_all_tables, set_server_loop

app = FastAPI(title="Vasuki", version="0.0.1-phase0")


@app.on_event("startup")
async def on_startup():
    create_all_tables()
    await connect()
    set_server_loop(asyncio.get_event_loop())


@app.on_event("shutdown")
async def on_shutdown():
    await disconnect()


@app.get("/health")
async def health():
    return {"status": "healthy", "phase": "0-foundation"}
