"""
tests/test_phase7_tts.py

INDEPENDENT verification for Phase 7. Copy verbatim.
Do not edit assertions to make them pass.

HOW TO RUN (no mic, no real audio output — all mocked):
    pytest tests/test_phase7_tts.py -v
"""
from unittest.mock import patch, MagicMock
import pytest

from app.services.tts_service import speak, interrupt, speak_and_wait
from app.services.executor_service import execute, _answer_question


# -- TTS service -------------------------------------------------------------

def test_speak_does_not_crash_on_empty_string():
    speak("")
    speak_and_wait("")


def test_speak_does_not_crash_on_none_engine():
    with patch("app.services.tts_service._get_pyttsx3_engine", return_value=None):
        speak("hello")
        speak_and_wait("hello")


def test_speak_runs_in_background():
    import time
    with patch("app.services.tts_service._speak_pyttsx3") as mock_speak:
        mock_speak.return_value = None
        speak("testing background thread")
        # speak() is non-blocking — should return immediately
        time.sleep(0.1)


def test_interrupt_does_not_crash_without_engine():
    with patch("app.services.tts_service._get_pyttsx3_engine", return_value=None):
        interrupt()


def test_speak_uses_pyttsx3_by_default():
    with patch("app.services.tts_service._USE_EDGE_TTS", False):
        with patch("app.services.tts_service._speak_pyttsx3") as mock_p:
            with patch("app.services.tts_service._speak_edge_tts") as mock_e:
                speak_and_wait("hello")
                mock_p.assert_called_once_with("hello")
                mock_e.assert_not_called()


def test_speak_uses_edge_tts_when_enabled():
    with patch("app.services.tts_service._USE_EDGE_TTS", True):
        with patch("app.services.tts_service._speak_edge_tts") as mock_e:
            with patch("app.services.tts_service._speak_pyttsx3") as mock_p:
                speak_and_wait("hello")
                mock_e.assert_called_once_with("hello")
                mock_p.assert_not_called()


# -- answer_question executor action -----------------------------------------

def test_answer_question_success():
    mock_response = {
        "message": {"content": "The speed of light is 299,792 kilometres per second."}
    }
    with patch("ollama.chat", return_value=mock_response):
        result = _answer_question({"question": "what is the speed of light"})
        assert result["success"] is True
        assert result["action"] == "answer_question"
        assert "299" in result["message"]
        assert result["data"]["answer"] == result["message"]


def test_answer_question_ollama_unavailable():
    with patch("ollama.chat", side_effect=Exception("connection refused")):
        result = _answer_question({"question": "what is the speed of light"})
        assert result["success"] is False
        assert result["action"] == "answer_question"
        assert len(result["message"]) > 0  # graceful fallback message


def test_answer_question_empty_question():
    result = _answer_question({"question": ""})
    assert result["success"] is False
    assert result["action"] == "answer_question"


def test_answer_question_result_has_four_keys():
    mock_response = {"message": {"content": "42 is the answer."}}
    with patch("ollama.chat", return_value=mock_response):
        result = _answer_question({"question": "what is the meaning of life"})
        assert set(result.keys()) == {"success", "action", "message", "data"}


def test_execute_routes_answer_question():
    mock_response = {"message": {"content": "Paris is the capital of France."}}
    with patch("ollama.chat", return_value=mock_response):
        result = execute({
            "action": "answer_question",
            "params": {"question": "what is the capital of France"}
        })
        assert result["success"] is True
        assert "Paris" in result["message"]


# -- start_vasuki.bat exists -------------------------------------------------

def test_start_vasuki_bat_exists():
    import os
    assert os.path.exists("start_vasuki.bat"), (
        "start_vasuki.bat not found in project root. "
        "Users need this for single-click startup."
    )


def test_start_vasuki_bat_has_required_commands():
    with open("start_vasuki.bat", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    assert "ollama serve" in content
    assert "uvicorn app.main:app" in content
    assert "console_listener.py" in content
