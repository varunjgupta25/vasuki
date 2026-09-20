"""
app/services/tts_service.py
Windows SAPI TTS via pywin32 (already installed with pyauto-desktop).
Runs on a dedicated thread with CoInitialize for COM compatibility.
"""
import os
import queue
import threading

_tts_queue = queue.Queue()
_USE_EDGE_TTS = os.getenv("USE_EDGE_TTS", "false").lower() == "true"


def _tts_worker():
    """Dedicated TTS thread with COM initialised."""
    import pythoncom
    pythoncom.CoInitialize()
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        while True:
            text = _tts_queue.get()
            if text is None:
                break
            try:
                if text:
                    speaker.Speak(text)
            except Exception as e:
                print(f"[TTS] error: {e}")
            _tts_queue.task_done()
    finally:
        pythoncom.CoUninitialize()


_worker = threading.Thread(target=_tts_worker, daemon=True)
_worker.start()


def speak(text: str) -> None:
    """Non-blocking — queues text for speech."""
    if not text or not text.strip():
        return
    _tts_queue.put(text)


def interrupt() -> None:
    """Clear the speech queue."""
    try:
        while not _tts_queue.empty():
            _tts_queue.get_nowait()
            _tts_queue.task_done()
    except Exception:
        pass


def speak_and_wait(text: str) -> None:
    """Blocking — waits until speech finishes."""
    if not text or not text.strip():
        return
    import app.services.tts_service as tts
    if tts._USE_EDGE_TTS:
        _speak_edge_tts(text)
    else:
        _speak_pyttsx3(text)


# Stubs kept for test compatibility
def _get_pyttsx3_engine():
    return True

def _speak_pyttsx3(text: str) -> None:
    speak(text)
    _tts_queue.join()

def _speak_edge_tts(text: str) -> None:
    speak(text)
    _tts_queue.join()