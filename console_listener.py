"""
console_listener.py
Phase 7 entry point: full pipeline with voice responses.

mic → VAD → STT → wake gate → intruder gate → sensitive filter
  → speaker verify → intent parse → execute → speak result → audit log

Vasuki now talks back:
- Short spoken confirmations for all executor actions
- Full spoken answers for answer_question
- Interrupts current speech when a new command arrives

Run with:
    python console_listener.py
Or double-click start_vasuki.bat for single-click startup.
Press Ctrl+C to stop.
"""
import threading

import numpy as np

from app.adapters.audio_capture_adapter import iter_microphone_chunks
from app.services.capture_segmenter import segment_audio
from app.services.vad_service import is_speech
from app.services.stt_service import transcribe
from app.services.hallucination_filter import is_real_speech
from app.services.wake_word_service import (
    contains_wake_word,
    contains_sleep_word,
    extract_command,
)
from app.services.biometric_service import verify_speaker, list_enrolled_users
from app.services.intent_service import parse_intent, prewarm_ollama
from app.services.executor_service import execute
from app.services.intruder_detection_service import (
    is_locked_out,
    record_failure,
    record_success,
)
from app.services.sensitive_filter_service import check_sensitive
from app.services.audit_service import (
    initialise as audit_init,
    log_execution,
    log_intrusion_attempt,
    log_sensitive_block,
)
from app.services.tts_service import speak, interrupt
from app.services.app_indexer_service import start_indexer

_awake = False
_current_user: str = "unknown"


def _tts_confirmation(intent: dict, result: dict) -> str:
    """Returns a short spoken confirmation for an executor result."""
    action = intent.get("action", "unknown")
    success = result.get("success", False)

    if not success:
        if action == "open_app":
            app = intent.get("params", {}).get("app", "that app")
            return f"Sorry, I couldn't open {app}."
        return "Sorry, that didn't work."

    if action == "open_app":
        app = intent.get("params", {}).get("app", "it")
        return f"Opened {app}."
    elif action == "take_screenshot":
        return "Screenshot saved."
    elif action == "web_search":
        query = intent.get("params", {}).get("query", "that")
        return f"Searching for {query}."
    elif action == "lock_pc":
        return "Locking your PC."
    elif action == "type_text":
        return "Done."
    elif action == "answer_question":
        answer = result.get("message", "I couldn't find an answer.")
        words = answer.split()
        if len(words) > 40:
            # Long answer — speak first 40 words, print full answer
            spoken = " ".join(words[:40]) + "... I've printed the full answer here."
            print(f"\n[Full Answer]\n{answer}\n")
            return spoken
        return answer
    elif action == "unknown":
        return "I didn't understand that. Could you try again?"
    return "Done."


def _process_command(text: str) -> None:
    """Sensitive filter → intent parse → execute → speak → audit."""
    # Interrupt any ongoing speech before processing
    interrupt()

    # Sensitive filter first
    filter_result = check_sensitive(text)
    if filter_result["blocked"]:
        log_sensitive_block(filter_result["category"])
        msg = f"Blocked. {filter_result['reason']}"
        print(f"[Sensitive] {msg}")
        speak(msg)
        return

    intent = parse_intent(text)
    result = execute(intent)

    log_execution(
        user_id=_current_user,
        action=intent["action"],
        success=result["success"],
        detail=result["message"],
    )

    confirmation = _tts_confirmation(intent, result)
    print(f"Heard   : {text}")
    print(f"Intent  : {intent}")
    print(f"Result  : {result}")
    print(f"Vasuki  : {confirmation}")
    speak(confirmation)


def main():
    global _awake, _current_user

    audit_init()
    start_indexer()  # background thread — non-blocking
    threading.Thread(target=prewarm_ollama, daemon=True).start()

    enrolled = list_enrolled_users()
    if not enrolled:
        print("[WARNING] No voice profiles enrolled. Run 'python enroll.py' first.")
        biometrics_active = False
    else:
        print(f"[Biometrics active] Enrolled users: {', '.join(enrolled)}")
        biometrics_active = True

    locked, remaining = is_locked_out()
    if locked:
        msg = f"Vasuki is locked due to intrusion attempts. Try again in {remaining}."
        print(f"[LOCKED] {msg}")
        speak(msg)

    startup_msg = "Vasuki is ready. Say Vasuki to wake me up."
    print(f"Vasuki Phase 7 — sleeping. Say 'Vasuki' to wake me up. Ctrl+C to stop.")
    speak(startup_msg)

    chunks = iter_microphone_chunks()

    for segment_chunks in segment_audio(chunks, silence_chunk_timeout=4):
        audio = np.concatenate(segment_chunks)

        if not is_speech(audio):
            continue

        text = transcribe(audio)

        if not is_real_speech(text):
            continue

        if not _awake:
            if not contains_wake_word(text):
                continue

            locked, remaining = is_locked_out()
            if locked:
                msg = f"Vasuki is locked. Try again in {remaining}."
                print(f"[LOCKED] {msg}")
                speak(msg)
                continue

            if biometrics_active:
                result = verify_speaker(audio)
                if not result["verified"]:
                    log_intrusion_attempt(result["similarity"])
                    locked_out, remaining = record_failure(result["similarity"])
                    if locked_out:
                        msg = f"Too many failed attempts. Vasuki locked for {remaining}."
                        print(f"[SECURITY] {msg}")
                    else:
                        msg = "Sorry, I didn't recognise your voice."
                        print(f"[Security] Speaker not recognised "
                              f"(similarity={result['similarity']:.4f}).")
                    speak(msg)
                    continue

                record_success()
                _current_user = result["user_id"]
                wake_msg = f"Hello {result['user_id']}. How can I help you?"
                print(f"\n[Vasuki awakened] Verified: {result['user_id']} "
                      f"(similarity={result['similarity']:.4f})")
                speak(wake_msg)
            else:
                print("\n[Vasuki awakened]")
                speak("Vasuki awakened. How can I help?")
                _current_user = "unknown"

            _awake = True
            command = extract_command(text)
            if command:
                _process_command(command)

        else:
            if contains_sleep_word(text):
                _awake = False
                farewell = "Goodbye. Going to sleep."
                print("[Vasuki sleeping]\n")
                speak(farewell)
            else:
                _process_command(text)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nVasuki stopped. Goodbye.")
