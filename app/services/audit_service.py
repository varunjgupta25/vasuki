"""
app/services/audit_service.py
DPDP-compliant structured audit logging with 30-day retention.

What IS logged:
  - event type, user_id, action name, success flag, timestamp
  - intrusion attempt: similarity score only
  - sensitive block: category only

What is NEVER logged:
  - raw transcripts (voice-to-text output)
  - actual sensitive content (card numbers, Aadhaar, etc.)
  - biometric embeddings or voice data

This is designed to be auditable for DPDP Act 2023 compliance without
storing personal data beyond what is strictly necessary.
"""
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional

_lock = threading.Lock()
_RETENTION_DAYS = 30


def _get_db_path() -> str:
    from app.core.config import settings
    return str(settings.SYSTEM_DB_PATH)


def _ensure_table() -> None:
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY,
                event TEXT NOT NULL,
                user_id TEXT,
                action TEXT,
                success INTEGER,
                detail TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()


def _purge_old_records() -> None:
    """Delete records older than RETENTION_DAYS — called on startup."""
    cutoff = (datetime.now() - timedelta(days=_RETENTION_DAYS)).isoformat()
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("DELETE FROM audit_events WHERE created_at < ?", (cutoff,))
        conn.commit()
        conn.close()


def initialise() -> None:
    """Call once on startup — creates table and purges old records."""
    _ensure_table()
    _purge_old_records()


def log_execution(
    user_id: str,
    action: str,
    success: bool,
    detail: Optional[str] = None,
) -> None:
    """Log a command execution. Does NOT log the raw transcript."""
    _ensure_table()
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            "INSERT INTO audit_events (event, user_id, action, success, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            ("execution", user_id, action, int(success), detail),
        )
        conn.commit()
        conn.close()


def log_intrusion_attempt(similarity: float) -> None:
    """Log a failed biometric attempt. Logs similarity score only — no transcript."""
    _ensure_table()
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            "INSERT INTO audit_events (event, detail) VALUES (?, ?)",
            ("intrusion_attempt", f"similarity={similarity:.4f}"),
        )
        conn.commit()
        conn.close()


def log_sensitive_block(category: str) -> None:
    """Log a sensitive content block. Logs category only — no actual content."""
    _ensure_table()
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            "INSERT INTO audit_events (event, detail) VALUES (?, ?)",
            ("sensitive_blocked", f"category={category}"),
        )
        conn.commit()
        conn.close()


def get_recent_events(limit: int = 50) -> list[dict]:
    """Returns the most recent audit events for inspection."""
    _ensure_table()
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        rows = conn.execute(
            "SELECT event, user_id, action, success, detail, created_at "
            "FROM audit_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
    return [
        {
            "event": r[0],
            "user_id": r[1],
            "action": r[2],
            "success": bool(r[3]) if r[3] is not None else None,
            "detail": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]
