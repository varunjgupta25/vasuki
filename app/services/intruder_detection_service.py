"""
app/services/intruder_detection_service.py
Tracks consecutive biometric failures, enforces lockout, and captures
a webcam photo of the intruder on lockout trigger.

Lockout is persisted to SQLite so restarting the app does not reset it.

Rules:
- 3 consecutive failures → 5-minute lockout
- On lockout trigger: attempt webcam photo (fails silently if no camera)
- Photo saved to var/data/intruder_photos/intruder_YYYYMMDD_HHMMSS.png
- Resets on successful biometric verification
- Audit log: similarity score + photo path only, NEVER the transcript
"""
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_lock = threading.Lock()
_LOCKOUT_MINUTES = 5
_MAX_FAILURES = 3


def _get_db_path() -> str:
    from app.core.config import settings
    return str(settings.SYSTEM_DB_PATH)


def _get_photo_dir() -> Path:
    from app.core.config import settings
    return settings.INTRUDER_PHOTO_DIR


def _ensure_table() -> None:
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intruder_lockouts (
                id INTEGER PRIMARY KEY,
                locked_until TEXT NOT NULL,
                fail_count INTEGER NOT NULL DEFAULT 0,
                last_similarity REAL,
                photo_path TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()


def _capture_intruder_photo() -> Optional[str]:
    """
    Attempts to capture one webcam frame and save it as evidence.
    Returns saved path on success, None on any failure.
    Never raises — missing or unavailable camera is handled gracefully.
    """
    try:
        import cv2
        photo_dir = _get_photo_dir()
        photo_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = photo_dir / f"intruder_{timestamp}.png"

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return None

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return None

        cv2.imwrite(str(save_path), frame)
        return str(save_path)
    except Exception:
        return None


def _get_active_lockout() -> Optional[dict]:
    """Returns active lockout record or None if not locked."""
    _ensure_table()
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        # Both locked_until and the comparison value are stored/compared in UTC
        row = conn.execute(
            "SELECT id, locked_until, fail_count FROM intruder_lockouts "
            "WHERE locked_until > datetime('now') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
    if row:
        # Parse as UTC-aware datetime
        locked_until = datetime.fromisoformat(row[1])
        if locked_until.tzinfo is None:
            # Legacy rows stored without tzinfo — treat as UTC
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        return {
            "id": row[0],
            "locked_until": locked_until,
            "fail_count": row[2],
        }
    return None


def _get_fail_count() -> int:
    """Returns current consecutive failure count (not yet locked)."""
    _ensure_table()
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        row = conn.execute(
            "SELECT fail_count FROM intruder_lockouts ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
    return row[0] if row else 0


def _upsert_fail_count(
    fail_count: int,
    similarity: float,
    locked_until: Optional[datetime] = None,
    photo_path: Optional[str] = None,
) -> None:
    if locked_until is None:
        # Expired immediately = not locked; use UTC so SQLite datetime('now') comparison works
        locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("DELETE FROM intruder_lockouts")
        conn.execute(
            "INSERT INTO intruder_lockouts "
            "(locked_until, fail_count, last_similarity, photo_path) "
            "VALUES (?, ?, ?, ?)",
            (locked_until.isoformat(), fail_count, similarity, photo_path),
        )
        conn.commit()
        conn.close()


def _clear_lockout() -> None:
    """Clear lockout on successful verification."""
    with _lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("DELETE FROM intruder_lockouts")
        conn.commit()
        conn.close()


def is_locked_out() -> tuple[bool, Optional[str]]:
    """Returns (True, 'Xm Ys remaining') if locked, (False, None) if not."""
    lockout = _get_active_lockout()
    if lockout:
        remaining = lockout["locked_until"] - datetime.now(timezone.utc)
        total_secs = int(remaining.total_seconds())
        if total_secs > 0:
            mins = total_secs // 60
            secs = total_secs % 60
            return True, f"{mins}m {secs}s"
    return False, None


def record_failure(similarity: float) -> tuple[bool, Optional[str]]:
    """
    Records a failed biometric attempt.
    On 3rd failure: captures webcam photo, triggers 5-minute lockout.
    Returns (locked_out: bool, time_remaining: str or None).
    """
    _ensure_table()
    current_fails = _get_fail_count()
    new_fails = current_fails + 1

    if new_fails >= _MAX_FAILURES:
        # Capture intruder photo before writing lockout
        photo_path = _capture_intruder_photo()
        # Use UTC so the stored timestamp is consistent with SQLite datetime('now') (UTC)
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
        _upsert_fail_count(new_fails, similarity, locked_until, photo_path)
        if photo_path:
            print(f"[Security] Intruder photo captured: {photo_path}")
        else:
            print("[Security] Webcam unavailable — no photo captured.")
        return True, f"{_LOCKOUT_MINUTES}m 0s"
    else:
        _upsert_fail_count(new_fails, similarity)
        return False, None


def record_success() -> None:
    """Clears lockout and failure count on successful biometric verification."""
    _clear_lockout()
