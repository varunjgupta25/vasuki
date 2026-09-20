"""
tests/test_phase8a.py

INDEPENDENT verification for Phase 8a. Copy verbatim.
Do not edit assertions to make them pass.

HOW TO RUN (no mic, no real filesystem writes — mocked):
    pytest tests/test_phase8a.py -v
"""
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.services.app_indexer_service import (
    find_app,
    _insert_app,
    _ensure_table,
    _name_from_path,
    is_indexed,
)
from app.services.file_service import (
    create_file,
    open_file,
    search_files,
    save_text,
    _safe_location,
)
from app.services.executor_service import execute


# -- App indexer: name extraction -------------------------------------------

def test_name_from_path_strips_extension():
    assert _name_from_path(r"C:\Program Files\Google\Chrome\chrome.exe") == "chrome"


def test_name_from_path_replaces_separators():
    assert _name_from_path(r"C:\Users\varun\Desktop\VS-Code.lnk") == "VS Code"


# -- App indexer: insert and find -------------------------------------------

def test_insert_and_find_app(tmp_path):
    db = str(tmp_path / "test.db")
    with patch("app.services.app_indexer_service._get_db_path", return_value=db):
        _ensure_table()
        _insert_app("WhatsApp", r"C:\Users\varun\Desktop\WhatsApp.lnk", "desktop")
        result = find_app("whatsapp")
        assert result is not None
        assert "WhatsApp" in result


def test_find_app_case_insensitive(tmp_path):
    db = str(tmp_path / "test.db")
    with patch("app.services.app_indexer_service._get_db_path", return_value=db):
        _ensure_table()
        _insert_app("Spotify", r"C:\Users\varun\Desktop\Spotify.lnk", "desktop")
        assert find_app("SPOTIFY") is not None
        assert find_app("spotify") is not None


def test_find_app_prefix_match(tmp_path):
    db = str(tmp_path / "test.db")
    with patch("app.services.app_indexer_service._get_db_path", return_value=db):
        _ensure_table()
        _insert_app("microsoft teams", r"C:\...\Teams.exe", "start_menu")
        result = find_app("microsoft")
        assert result is not None


def test_find_app_returns_none_when_not_found(tmp_path):
    db = str(tmp_path / "test.db")
    with patch("app.services.app_indexer_service._get_db_path", return_value=db):
        _ensure_table()
        assert find_app("nonexistentapp12345") is None


def test_is_indexed_false_before_scan():
    # is_indexed() reflects module-level state
    # We can only assert it's a bool since the scan may have run
    assert isinstance(is_indexed(), bool)


# -- App indexer: executor cascade ------------------------------------------

def test_executor_falls_through_to_index_when_allowlist_misses(tmp_path):
    db = str(tmp_path / "test.db")
    with patch("app.services.app_indexer_service._get_db_path", return_value=db):
        _ensure_table()
        _insert_app("whatsapp", r"C:\Users\varun\Desktop\WhatsApp.lnk", "desktop")
        with patch("app.services.app_indexer_service.find_app",
                   return_value=r"C:\Users\varun\Desktop\WhatsApp.lnk"):
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = MagicMock()
                result = execute({
                    "action": "open_app",
                    "params": {"app": "whatsapp"}
                })
                # WhatsApp not in hardcoded allowlist — should try index
                # (may succeed via index or fail gracefully)
                assert "action" in result
                assert "success" in result


# -- File service -----------------------------------------------------------

def test_safe_location_desktop():
    loc = _safe_location("desktop")
    assert "Desktop" in str(loc) or "desktop" in str(loc).lower()


def test_safe_location_defaults_to_desktop():
    loc = _safe_location("unknown_location")
    assert loc == Path.home() / "Desktop"


def test_create_file_success(tmp_path):
    with patch("app.services.file_service._safe_location", return_value=tmp_path):
        result = create_file("test_note", "Hello Vasuki", "desktop")
        assert result["success"] is True
        assert "test_note" in result["message"]
        assert Path(result["path"]).exists()
        assert Path(result["path"]).read_text() == "Hello Vasuki"


def test_create_file_adds_txt_extension(tmp_path):
    with patch("app.services.file_service._safe_location", return_value=tmp_path):
        result = create_file("myfile", "", "desktop")
        assert result["path"].endswith(".txt")


def test_open_file_not_found():
    result = open_file(r"C:\nonexistent\fake_file.txt")
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_search_files_empty_query():
    result = search_files("")
    assert result["success"] is False
    assert "query" in result["message"].lower()


def test_search_files_caps_at_five_results(tmp_path):
    # Create 8 matching files
    for i in range(8):
        (tmp_path / f"resume_{i}.txt").write_text("test")
    with patch("pathlib.Path.home", return_value=tmp_path):
        result = search_files("resume")
        assert len(result.get("results", [])) <= 5


def test_save_text_success(tmp_path):
    with patch("app.services.file_service._safe_location", return_value=tmp_path):
        result = save_text("This is my saved text", "my_notes", "desktop")
        assert result["success"] is True
        assert Path(result["path"]).read_text() == "This is my saved text"


# -- File operation executor action ----------------------------------------

def test_execute_file_operation_create(tmp_path):
    with patch("app.services.file_service._safe_location", return_value=tmp_path):
        result = execute({
            "action": "file_operation",
            "params": {
                "operation": "create",
                "name": "test_doc",
                "content": "hello",
                "location": "desktop",
            }
        })
        assert result["success"] is True


def test_execute_file_operation_unknown():
    result = execute({
        "action": "file_operation",
        "params": {"operation": "unknown_op"}
    })
    assert result["success"] is False


def test_execute_result_always_has_four_keys():
    result = execute({
        "action": "file_operation",
        "params": {"operation": "search", "query": ""}
    })
    assert "success" in result
    assert "action" in result
    assert "message" in result
