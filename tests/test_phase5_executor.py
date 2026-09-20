"""
tests/test_phase5_executor.py

INDEPENDENT verification for Phase 5. Copy verbatim.
Do not edit assertions to make them pass.

HOW TO RUN (no server, no mic, no real Windows calls — all mocked):
    pytest tests/test_phase5_executor.py -v
"""
from unittest.mock import patch, MagicMock
import pytest
from app.services.executor_service import (
    execute,
    APP_ALLOWLIST,
    _open_app,
    _lock_pc,
    _take_screenshot,
    _type_text,
    _web_search,
    _unknown,
    _SHELL_METACHARACTERS,
    _TYPE_TEXT_MAX_LEN,
)


# -- Allowlist & normalisation -----------------------------------------------

def test_allowlist_has_notepad():
    from app.services.intent_service import normalise
    assert normalise("notepad") in APP_ALLOWLIST
    assert normalise("note pad") in APP_ALLOWLIST


def test_allowlist_has_chrome():
    from app.services.intent_service import normalise
    assert normalise("chrome") in APP_ALLOWLIST
    assert normalise("google chrome") in APP_ALLOWLIST


def test_app_not_in_allowlist_returns_failure():
    result = _open_app({"app": "malware.exe"})
    assert result["success"] is False
    assert result["action"] == "open_app"
    assert "allowlist" in result["message"].lower()


# -- open_app ----------------------------------------------------------------

def test_open_app_success(tmp_path):
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        result = _open_app({"app": "notepad"})
        assert result["success"] is True
        assert result["action"] == "open_app"
        mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


def test_open_app_file_not_found():
    with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
        result = _open_app({"app": "notepad"})
        assert result["success"] is False
        assert "not found" in result["message"].lower()


def test_open_app_case_insensitive():
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        result = _open_app({"app": "NOTEPAD"})
        assert result["success"] is True


# -- lock_pc -----------------------------------------------------------------

def test_lock_pc_success():
    with patch("ctypes.windll.user32.LockWorkStation", return_value=1):
        result = _lock_pc({})
        assert result["success"] is True
        assert result["action"] == "lock_pc"


def test_lock_pc_failure():
    with patch("ctypes.windll.user32.LockWorkStation", return_value=0):
        result = _lock_pc({})
        assert result["success"] is False
        assert "failed" in result["message"].lower()


# -- take_screenshot ---------------------------------------------------------

def test_take_screenshot_success(tmp_path):
    mock_img = MagicMock()
    with patch("PIL.ImageGrab.grab", return_value=mock_img):
        with patch("app.services.executor_service._get_screenshots_dir",
                   return_value=tmp_path):
            result = _take_screenshot({})
            assert result["success"] is True
            assert result["action"] == "take_screenshot"
            assert "path" in result["data"]
            assert "screenshot_" in result["data"]["path"]


def test_take_screenshot_path_in_data(tmp_path):
    mock_img = MagicMock()
    with patch("PIL.ImageGrab.grab", return_value=mock_img):
        with patch("app.services.executor_service._get_screenshots_dir",
                   return_value=tmp_path):
            result = _take_screenshot({})
            assert result["data"]["path"].endswith(".png")


# -- type_text ---------------------------------------------------------------

def test_type_text_rejects_long_text():
    long_text = "a" * (_TYPE_TEXT_MAX_LEN + 1)
    result = _type_text({"text": long_text})
    assert result["success"] is False
    assert "too long" in result["message"].lower()


def test_type_text_rejects_metacharacters():
    for char in ["&", "|", ";", "`", "$"]:
        result = _type_text({"text": f"hello{char}world"})
        assert result["success"] is False, f"Should reject '{char}'"
        assert "banned" in result["message"].lower()


def test_type_text_success():
    with patch("pyauto_desktop.typewrite") as mock_type:
        with patch("app.services.executor_service.sleep"):
            result = _type_text({"text": "hello world"})
            assert result["success"] is True
            assert result["action"] == "type_text"
            mock_type.assert_called_once_with("hello world")


# -- web_search --------------------------------------------------------------

def test_web_search_success():
    with patch("webbrowser.open") as mock_open:
        result = _web_search({"query": "python tutorials"})
        assert result["success"] is True
        assert result["action"] == "web_search"
        called_url = mock_open.call_args[0][0]
        assert "google.com/search" in called_url
        assert "python" in called_url


def test_web_search_empty_query():
    result = _web_search({"query": ""})
    assert result["success"] is False
    assert "query" in result["message"].lower()


# -- unknown & unsupported actions ------------------------------------------

def test_unknown_action_handled():
    result = _unknown({"raw": "do something weird"})
    assert result["success"] is False
    assert result["action"] == "unknown"


def test_unsupported_action_via_execute():
    result = execute({"action": "reminder", "params": {"reminder": "drink water"}})
    assert result["success"] is False
    assert "not supported" in result["message"].lower()
    assert result["action"] == "reminder"


# -- Result schema -----------------------------------------------------------

def test_result_always_has_four_keys():
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        result = execute({"action": "open_app", "params": {"app": "notepad"}})
        assert set(result.keys()) == {"success", "action", "message", "data"}

    result2 = execute({"action": "unknown", "params": {"raw": "test"}})
    assert set(result2.keys()) == {"success", "action", "message", "data"}

    result3 = execute({"action": "invented_action", "params": {}})
    assert set(result3.keys()) == {"success", "action", "message", "data"}


def test_execute_never_raises():
    # Should never raise even with completely malformed input
    result = execute({})
    assert isinstance(result, dict)
    assert "success" in result

    result2 = execute({"action": None, "params": None})
    assert isinstance(result2, dict)
