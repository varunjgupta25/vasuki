"""
tests/test_phase4_intent.py

INDEPENDENT verification for Phase 4. Copy verbatim.
Do not edit assertions to make them pass.

HOW TO RUN (no server, no mic, no Ollama needed):
    pytest tests/test_phase4_intent.py -v
"""
from unittest.mock import patch, MagicMock
import pytest
from app.services.intent_service import (
    normalise,
    parse_intent,
    _try_regex,
    _try_cache,
    _cache_set,
    _cache_get,
    _parse_ollama_response,
    _fallback,
)


# -- Normalisation -----------------------------------------------------------

def test_normalise_lowercase():
    assert normalise("Open Notepad!") == "open notepad"


def test_normalise_strips_punctuation():
    assert normalise("lock the pc.") == "lock the pc"


def test_normalise_collapses_whitespace():
    assert normalise("open  notepad") == "open notepad"


def test_normalise_same_result_for_variants():
    assert normalise("Open Notepad!") == normalise("open notepad")


# -- Regex tier --------------------------------------------------------------

def test_regex_open_app():
    result = _try_regex("open notepad")
    assert result is not None
    assert result["action"] == "open_app"
    assert result["params"]["app"] == "notepad"
    assert result["source"] == "regex"
    assert result["confidence"] == 1.0


def test_regex_launch_synonym():
    result = _try_regex("launch chrome")
    assert result is not None
    assert result["action"] == "open_app"
    assert result["params"]["app"] == "chrome"


def test_regex_lock_pc():
    result = _try_regex("lock the pc")
    assert result is not None
    assert result["action"] == "lock_pc"
    assert result["params"] == {}


def test_regex_screenshot():
    result = _try_regex("take a screenshot")
    assert result is not None
    assert result["action"] == "take_screenshot"


def test_regex_type_text():
    result = _try_regex("type hello world")
    assert result is not None
    assert result["action"] == "type_text"
    assert result["params"]["text"] == "hello world"


def test_regex_web_search():
    result = _try_regex("search for python tutorials")
    assert result is not None
    assert result["action"] == "web_search"
    assert result["params"]["query"] == "python tutorials"


def test_regex_returns_none_on_unknown():
    result = _try_regex("xyzzy frobnicate")
    assert result is None


# -- Cache tier --------------------------------------------------------------

def test_cache_miss_returns_none(tmp_path):
    with patch("app.services.intent_service._get_db_path",
               return_value=str(tmp_path / "test.db")):
        result = _try_cache("open notepad")
        assert result is None


def test_cache_set_then_get(tmp_path):
    db = str(tmp_path / "test.db")
    with patch("app.services.intent_service._get_db_path", return_value=db):
        from app.services.intent_service import _ensure_cache_table
        _ensure_cache_table()
        intent = {
            "action": "open_app",
            "params": {"app": "notepad"},
            "confidence": 0.9,
            "source": "ollama",
        }
        _cache_set("open notepad", intent)
        result = _cache_get(normalise("open notepad"))
        assert result is not None
        assert result["action"] == "open_app"
        assert result["source"] == "cache"


def test_cache_normalises_key(tmp_path):
    db = str(tmp_path / "test.db")
    with patch("app.services.intent_service._get_db_path", return_value=db):
        from app.services.intent_service import _ensure_cache_table
        _ensure_cache_table()
        intent = {
            "action": "open_app",
            "params": {"app": "notepad"},
            "confidence": 0.9,
            "source": "ollama",
        }
        _cache_set("Open Notepad!", intent)
        result = _cache_get(normalise("open notepad"))
        assert result is not None


# -- Ollama JSON parsing -----------------------------------------------------

def test_parse_ollama_valid_json():
    raw = '{"action": "open_app", "params": {"app": "notepad"}, "confidence": 0.95}'
    result = _parse_ollama_response(raw)
    assert result is not None
    assert result["action"] == "open_app"
    assert result["source"] == "ollama"


def test_parse_ollama_strips_markdown_fences():
    raw = '```json\n{"action": "lock_pc", "params": {}, "confidence": 1.0}\n```'
    result = _parse_ollama_response(raw)
    assert result is not None
    assert result["action"] == "lock_pc"


def test_parse_ollama_malformed_returns_none():
    assert _parse_ollama_response("this is not json") is None
    assert _parse_ollama_response("") is None
    assert _parse_ollama_response("{broken}") is None


# -- Fallback ----------------------------------------------------------------

def test_fallback_shape():
    result = _fallback("xyzzy frobnicate")
    assert result["action"] == "unknown"
    assert result["source"] == "fallback"
    assert result["confidence"] == 0.0
    assert "raw" in result["params"]


# -- Full cascade (Ollama mocked) --------------------------------------------

def test_parse_intent_regex_path():
    result = parse_intent("open notepad")
    assert result["action"] == "open_app"
    assert result["source"] == "regex"


def test_parse_intent_ollama_unavailable_returns_fallback():
    with patch("app.services.intent_service._try_ollama", return_value=None):
        result = parse_intent("do something completely unknown xyzzy")
        assert result["action"] == "unknown"
        assert result["source"] == "fallback"


def test_parse_intent_always_has_four_keys():
    result = parse_intent("open notepad")
    assert set(result.keys()) == {"action", "params", "confidence", "source"}

    with patch("app.services.intent_service._try_ollama", return_value=None):
        result2 = parse_intent("xyzzy frobnicator unknown command")
        assert set(result2.keys()) == {"action", "params", "confidence", "source"}
