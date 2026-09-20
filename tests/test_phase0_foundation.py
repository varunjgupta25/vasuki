"""
tests/test_phase0_foundation.py

This is the success-criteria oracle for Phase 0. Copy it exactly as written —
do not edit its assertions to make them pass. If something here seems wrong,
flag it in your final report instead of weakening it.

HOW IT'S RUN (you, the agent, must do this in your loop):
1. Start the server in the background: uvicorn app.main:app
2. From the project root: pytest tests/test_phase0_foundation.py -v
3. All tests must pass. Restart the server and run again — must pass
   identically the second time before you report done.
"""
import os
import sqlite3

import pytest
import requests

DB_PATH = os.path.join("var", "data", "vasuki.db")
HEALTH_URL = "http://127.0.0.1:8000/health"


def test_no_hardcoded_identity():
    """Fails if 'varun' or 'owner' appears anywhere in app/ source."""
    hits = []
    for root, _, files in os.walk("app"):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    content = fh.read().lower()
                    if "varun" in content or "owner" in content:
                        hits.append(path)
    assert not hits, f"Hardcoded identity references found in: {hits}"


def test_no_network_imports():
    """Phase 0 must not import any outbound HTTP client inside app/."""
    banned = ("requests", "httpx", "urllib.request")
    hits = []
    for root, _, files in os.walk("app"):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    for b in banned:
                        if f"import {b}" in content:
                            hits.append((path, b))
    assert not hits, f"Found banned network imports: {hits}"


def test_health_endpoint_responds():
    """Server must already be running (uvicorn app.main:app) for this test."""
    try:
        r = requests.get(HEALTH_URL, timeout=3)
    except requests.exceptions.ConnectionError:
        pytest.skip("Server not running — start uvicorn first or use start_vasuki.bat")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "healthy"
    assert body.get("phase") == "0-foundation"


def test_db_file_exists_after_boot():
    """Server must have booted at least once before this runs."""
    assert os.path.exists(DB_PATH), (
        "vasuki.db was not created. Start the server once "
        "(uvicorn app.main:app) then re-run this test."
    )


def test_schema_has_user_id_columns():
    """Every user-scoped table must support multiple users, not one."""
    assert os.path.exists(DB_PATH), "DB doesn't exist yet — boot the server first."
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for table in ("speaker_profiles", "command_history", "audit_log"):
        cur.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cur.fetchall()]
        assert columns, f"Table {table} does not exist"
        assert "user_id" in columns, f"{table} is missing a user_id column"
    conn.close()


def test_db_uses_threading_lock_not_asyncio_lock():
    """Catches the cross-loop concurrency bug before six more phases
    get built on top of it."""
    db_file_path = os.path.join("app", "db", "database.py")
    assert os.path.exists(db_file_path), "app/db/database.py not found"
    with open(db_file_path, encoding="utf-8") as fh:
        content = fh.read()
    assert "threading.Lock" in content, "database.py must use threading.Lock"
    assert "asyncio.Lock" not in content, (
        "database.py must NOT use asyncio.Lock — this breaks across "
        "the voice-thread / server-loop boundary later."
    )
