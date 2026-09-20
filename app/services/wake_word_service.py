"""
app/services/wake_word_service.py
Pure, stateless wake word and sleep word detection.

These are string-matching functions only — no model loading, no hardware,
no global state. All state (awake vs sleeping) lives in console_listener.py,
not here. This keeps the logic fully unit-testable without a microphone.
"""

WAKE_WORDS = [
    "vasuki",
    "om namah shivaya",
    "om namah shiv",
    "wake up",
]

SLEEP_WORDS = [
    "goodbye",
    "good bye",
    "go to sleep",
    "sleep",
    "good night",
    "rest",
]


def contains_wake_word(text: str) -> bool:
    """Returns True if the transcript contains any wake word."""
    clean = text.strip().lower()
    return any(w in clean for w in WAKE_WORDS)


def contains_sleep_word(text: str) -> bool:
    """Returns True if the transcript contains any sleep word."""
    clean = text.strip().lower()
    return any(w in clean for w in SLEEP_WORDS)


def extract_command(text: str) -> str:
    """
    Strips the wake word from the transcript so the rest of the pipeline
    receives the actual command, not the wake word itself.

    Example: "Vasuki open notepad" → "open notepad"
    If no wake word is found, returns the original text unchanged.
    """
    clean = text.strip()
    lower = clean.lower()
    for w in WAKE_WORDS:
        if lower.startswith(w):
            return clean[len(w):].strip(" ,.")
    return clean
