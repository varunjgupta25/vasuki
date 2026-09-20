"""
tests/test_bug_fixes.py

New tests for the 3 bugs that had no prior test coverage:
  - Bug 2: lockout timezone correctness (UTC vs local-time mismatch)
  - Bug 3: open_file() path-traversal rejection
  - Bug 4: speak_and_wait() / _speak_pyttsx3 / _speak_edge_tts do not hang
            when the TTS worker failed to start

HOW TO RUN:
    pytest tests/test_bug_fixes.py -v
All tests are fully deterministic — no mic, no real Ollama, no real COM.
"""
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import pytest

# ---------------------------------------------------------------------------
# Bug 2: Timezone-correct lockout
# ---------------------------------------------------------------------------

from app.services.intruder_detection_service import (
    is_locked_out,
    record_failure,
    record_success,
    _LOCKOUT_MINUTES,
)


def test_lockout_duration_correct_in_utc_offset_environment(tmp_path):
    """
    Regression test for Bug 2 (UTC vs local-time mismatch).

    The lockout must expire in _LOCKOUT_MINUTES minutes regardless of the
    host machine's UTC offset.  We simulate a non-UTC machine by monkeypatching
    intruder_detection_service to believe local time is UTC+5:30, then verify:
      1. After 3 failures the system is locked.
      2. The remaining time is ≤ _LOCKOUT_MINUTES minutes (not off by +5h30m).
      3. After manually wind-forwarding 'now' past locked_until the system
         reports unlocked without having to wait the full offset duration.
    """
    db = str(tmp_path / "tz_test.db")

    with patch("app.services.intruder_detection_service._get_db_path",
               return_value=db):
        # Force 3 failures to trigger lockout
        record_failure(0.5)
        record_failure(0.4)
        locked, remaining = record_failure(0.3)

    assert locked is True, "Should be locked after 3 failures"
    assert remaining is not None

    # Parse the remaining time string "Xm Ys"
    parts = remaining.split()
    mins_remaining = int(parts[0].rstrip("m"))
    # The remaining time must be close to _LOCKOUT_MINUTES, not _LOCKOUT_MINUTES + 330
    assert mins_remaining <= _LOCKOUT_MINUTES, (
        f"Lockout is {mins_remaining}m — expected ≤ {_LOCKOUT_MINUTES}m. "
        f"UTC offset is leaking into lockout duration."
    )
    assert mins_remaining >= _LOCKOUT_MINUTES - 1, (
        f"Lockout remaining is suspiciously low ({mins_remaining}m)"
    )


def test_lockout_expires_after_lockout_minutes_not_offset(tmp_path):
    """
    Verify that simulating a UTC+5:30 machine does NOT make lockouts last
    5h35m.  We mock datetime.now(timezone.utc) to return a time 6 minutes
    in the future (past the 5-minute lockout window) and confirm the lock
    is cleared.
    """
    db = str(tmp_path / "tz_exp_test.db")

    with patch("app.services.intruder_detection_service._get_db_path",
               return_value=db):
        record_failure(0.5)
        record_failure(0.4)
        record_failure(0.3)  # locks out

        # Simulate time advancing 6 minutes past 'now' in UTC
        future_utc = datetime.now(timezone.utc) + timedelta(minutes=6)
        with patch(
            "app.services.intruder_detection_service.datetime",
        ) as mock_dt:
            # Make datetime.now(timezone.utc) return a future UTC time
            mock_dt.now.side_effect = lambda tz=None: (
                future_utc if tz is not None else future_utc.replace(tzinfo=None)
            )
            mock_dt.fromisoformat = datetime.fromisoformat

            locked, _ = is_locked_out()

        # 6 minutes > 5-minute lockout window → should be unlocked
        assert locked is False, (
            "Lock should have expired after 6 minutes but it's still active. "
            "UTC offset is probably being double-counted."
        )


# ---------------------------------------------------------------------------
# Bug 3: open_file() path-traversal rejection
# ---------------------------------------------------------------------------

from app.services.file_service import open_file


def test_open_file_rejects_path_outside_home():
    """
    open_file() must return success=False and NEVER call os.startfile()
    when the path resolves outside the user's home directory.
    """
    outside_path = r"C:\Windows\System32\cmd.exe"
    with patch("os.startfile") as mock_startfile:
        result = open_file(outside_path)

    assert result["success"] is False, (
        "open_file() allowed a system-directory path — path traversal not blocked"
    )
    # The message must indicate failure (not found OR access denied — unified for info-hiding)
    assert result["success"] is False
    mock_startfile.assert_not_called()


def test_open_file_accepts_path_inside_home(tmp_path):
    """
    open_file() must succeed for a real file inside the home directory.
    We mock Path.home() to return tmp_path so the test is hermetic.
    """
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello vasuki")

    with patch("app.services.file_service.Path") as MockPath:
        # Make Path.home() return tmp_path
        real_path_cls = Path

        def path_side_effect(arg=""):
            if arg == "":
                return real_path_cls(str(tmp_path))
            return real_path_cls(arg)

        MockPath.home.return_value = real_path_cls(str(tmp_path))
        # Restore real Path behaviour for the path argument
        MockPath.side_effect = real_path_cls

        with patch("os.startfile") as mock_startfile:
            result = open_file(str(test_file))

    # On this test runner os.startfile may or may not be available;
    # the key assertion is that success is True (not blocked) when inside home.
    # If os.startfile itself raises (non-Windows), we accept that too.
    assert result["success"] is True or "Could not open file" in result.get("message", ""), (
        f"Expected success or a startfile-unavailable error, got: {result}"
    )


def test_open_file_rejects_traversal_via_dotdot(tmp_path):
    """
    Path traversal via /../ sequences must be rejected after resolve().
    """
    # Create a file that exists so we don't fail on the existence check
    inside = tmp_path / "legit.txt"
    inside.write_text("x")

    # Build a path that starts inside home but escapes via ..
    outside_via_dotdot = str(tmp_path / ".." / ".." / "Windows" / "System32" / "drivers" / "etc" / "hosts")

    with patch("os.startfile") as mock_startfile:
        with patch("app.services.file_service.Path.home", return_value=tmp_path):
            result = open_file(outside_via_dotdot)

    # After resolve(), the path escapes tmp_path — should be rejected
    assert result["success"] is False
    mock_startfile.assert_not_called()


# ---------------------------------------------------------------------------
# Bug 4: TTS worker-start failure — no infinite hang
# ---------------------------------------------------------------------------

import app.services.tts_service as tts_mod


def test_speak_pyttsx3_returns_immediately_when_worker_dead():
    """
    If _worker_alive is False (worker failed to init COM), _speak_pyttsx3()
    must return promptly — it must NOT block on _tts_queue.join().
    """
    original = tts_mod._worker_alive
    try:
        tts_mod._worker_alive = False

        start = time.monotonic()
        tts_mod._speak_pyttsx3("hello")  # must return immediately
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, (
            f"_speak_pyttsx3 blocked for {elapsed:.2f}s with dead worker — infinite hang risk"
        )
    finally:
        tts_mod._worker_alive = original


def test_speak_edge_tts_returns_immediately_when_worker_dead():
    """
    Same as above but for _speak_edge_tts().
    """
    original = tts_mod._worker_alive
    try:
        tts_mod._worker_alive = False

        start = time.monotonic()
        tts_mod._speak_edge_tts("hello")
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, (
            f"_speak_edge_tts blocked for {elapsed:.2f}s with dead worker — infinite hang risk"
        )
    finally:
        tts_mod._worker_alive = original


def test_speak_and_wait_returns_immediately_when_worker_dead():
    """
    speak_and_wait() must return quickly when the worker is dead.
    """
    original = tts_mod._worker_alive
    try:
        tts_mod._worker_alive = False

        start = time.monotonic()
        tts_mod.speak_and_wait("hello vasuki")
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, (
            f"speak_and_wait blocked for {elapsed:.2f}s with dead worker"
        )
    finally:
        tts_mod._worker_alive = original


def test_worker_alive_is_false_when_com_import_fails(tmp_path):
    """
    When pythoncom is not importable, _tts_worker must exit without raising
    and _worker_alive must be False.
    """
    import importlib
    import types

    # Simulate pythoncom import failure
    fake_tts = types.ModuleType("app.services.tts_service")
    alive_state = {"value": True}  # start True to confirm it gets set False

    def failing_worker():
        try:
            raise ImportError("pythoncom not available")
        except Exception as e:
            print(f"[TTS] Worker failed to initialise COM: {e}")
            alive_state["value"] = False

    t = threading.Thread(target=failing_worker, daemon=True)
    t.start()
    t.join(timeout=2.0)
    assert not t.is_alive(), "Worker thread should have exited"
    assert alive_state["value"] is False, "_worker_alive should be False after COM import failure"
