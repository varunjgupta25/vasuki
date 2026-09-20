"""
tests/test_phase2_wake_word.py

INDEPENDENT verification for Phase 2. Copy verbatim — do not edit
assertions to make them pass.

HOW TO RUN (no server needed):
    pytest tests/test_phase2_wake_word.py -v
Run it as many times as you want — fully deterministic, no hardware needed.
"""
from app.services.wake_word_service import (
    contains_wake_word,
    contains_sleep_word,
    extract_command,
)


# -- Wake word detection -----------------------------------------------------

def test_detects_vasuki_wake_word():
    assert contains_wake_word("vasuki") is True
    assert contains_wake_word("Vasuki") is True
    assert contains_wake_word("  VASUKI  ") is True


def test_detects_vasuki_in_sentence():
    assert contains_wake_word("vasuki open notepad") is True
    assert contains_wake_word("hey vasuki what time is it") is True


def test_detects_om_namah_shivaya():
    assert contains_wake_word("om namah shivaya") is True
    assert contains_wake_word("Om Namah Shivaya open chrome") is True


def test_detects_wake_up():
    assert contains_wake_word("wake up") is True


def test_no_false_positive_wake_words():
    assert contains_wake_word("open notepad please") is False
    assert contains_wake_word("what time is it") is False
    assert contains_wake_word("") is False


# -- Sleep word detection ----------------------------------------------------

def test_detects_sleep_words():
    assert contains_sleep_word("goodbye") is True
    assert contains_sleep_word("go to sleep") is True
    assert contains_sleep_word("good night") is True
    assert contains_sleep_word("rest now") is True
    assert contains_sleep_word("sleep") is True


def test_sleep_words_case_insensitive():
    assert contains_sleep_word("Goodbye") is True
    assert contains_sleep_word("GOOD NIGHT") is True


def test_no_false_positive_sleep_words():
    assert contains_sleep_word("vasuki open notepad") is False
    assert contains_sleep_word("what is the time") is False
    assert contains_sleep_word("") is False


# -- Command extraction ------------------------------------------------------

def test_extract_command_strips_vasuki_prefix():
    assert extract_command("vasuki open notepad") == "open notepad"
    assert extract_command("Vasuki open notepad") == "open notepad"


def test_extract_command_strips_om_namah_shivaya():
    assert extract_command("om namah shivaya open chrome") == "open chrome"


def test_extract_command_returns_original_if_no_wake_word():
    assert extract_command("open notepad") == "open notepad"


def test_extract_command_returns_empty_if_only_wake_word():
    result = extract_command("vasuki")
    assert result == ""


def test_extract_command_strips_punctuation():
    assert extract_command("vasuki, open notepad") == "open notepad"
