"""
app/services/hallucination_filter.py
Rejects known Faster-Whisper hallucinations on near-silent/noisy audio.

This is a basic Phase 1 version. Wake-word-aware filtering (so a single
spoken wake word like "Vasuki" isn't rejected for being short) arrives
in Phase 2 alongside wake-word detection itself.
"""

HALLUCINATION_PHRASES = {
    "thank you",
    "thanks for watching",
    "you",
    "bye",
    "subtitles by",
    "subscribe",
    "like and subscribe",
    "the machine",
    "i'm out",
    "where are you",
    "wake up",
    "wake",
}


def is_real_speech(text: str) -> bool:
    if not text:
        return False
    clean = text.strip(" .?!,").lower()
    if len(clean) < 2:
        return False
    if clean in HALLUCINATION_PHRASES:
        return False
    return True
