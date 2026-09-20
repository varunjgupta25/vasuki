"""
app/services/tts_service.py
Windows SAPI TTS via pywin32 (already installed with pyauto-desktop).
Runs on a dedicated thread with CoInitialize for COM compatibility.

Bug-4 fix: if _tts_worker fails to start (import error, COM init error, or any
other startup exception) _worker_alive is set to False and all blocking
speak_and_wait() / _speak_pyttsx3() / _speak_edge_tts() calls detect this and
return immediately instead of hanging forever on _tts_queue.join().
"""
import os
import queue
import threading

_tts_queue = queue.Queue()
_USE_EDGE_TTS = os.getenv("USE_EDGE_TTS", "false").lower() == "true"

# Whether the worker thread started successfully and is running
_worker_alive = False


def _tts_worker():
    """Dedicated TTS thread with COM initialised."""
    global _worker_alive
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception as e:
        # COM or pythoncom import failed — mark dead so callers don't hang
        print(f"[TTS] Worker failed to initialise COM: {e}")
        _worker_alive = False
        return

    _worker_alive = True
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
    except Exception as e:
        print(f"[TTS] Worker crashed: {e}")
        _worker_alive = False
    finally:
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass


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
    """Blocking — waits until speech finishes.

    If the worker is dead (failed to start), returns immediately instead of
    hanging. Uses _speak_edge_tts or _speak_pyttsx3 based on USE_EDGE_TTS env.
    """
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
    """Speak via the SAPI queue and block until done (if worker is alive)."""
    if not _worker_alive:
        print("[TTS] _speak_pyttsx3: worker not alive, skipping.")
        return
    speak(text)
    _tts_queue.join()  # safe: worker is alive, will call task_done()


def _speak_edge_tts(text: str) -> None:
    """Speak via the SAPI queue and block until done (if worker is alive)."""
    if not _worker_alive:
        print("[TTS] _speak_edge_tts: worker not alive, skipping.")
        return
    speak(text)
    _tts_queue.join()  # safe: worker is alive, will call task_done()