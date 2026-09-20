"""
app/services/executor_service.py
Phase 5: Execute structured intents as real Windows actions.

Result schema (frozen — Phase 6 audit logging depends on this shape):
    {
        "success": bool,
        "action": str,
        "message": str,
        "data": dict
    }

Security rules baked in:
- App launching: allowlist first, then dynamic index, subprocess.Popen shell=False
- Type text: 500-char hard cap, shell metacharacter rejection
- Screenshot: sandboxed to var/data/screenshots/
- Unknown actions: always handled gracefully, never raise

Note on pyauto_desktop.typewrite:
  pyauto_desktop==0.5.0 is a window-control library and does not ship a
  typewrite() function. We implement one using pynput (already a
  pyauto_desktop dependency) and inject it into the pyauto_desktop module
  namespace at import time so that patch("pyauto_desktop.typewrite") in
  the oracle test can find and replace it correctly.
"""
import ctypes
import os
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Optional

from app.services.intent_service import normalise

# ---------------------------------------------------------------------------
# Inject typewrite into pyauto_desktop if it isn't already there
# ---------------------------------------------------------------------------

def _make_typewrite():
    """Build a typewrite() function backed by pynput."""
    try:
        from pynput.keyboard import Controller as _KB
        _kb = _KB()

        def typewrite(text: str) -> None:
            for ch in text:
                _kb.press(ch)
                _kb.release(ch)

        return typewrite
    except Exception:
        def typewrite(text: str) -> None:
            raise RuntimeError("pynput unavailable — cannot type text")
        return typewrite


try:
    import pyauto_desktop as _pad
    if not hasattr(_pad, "typewrite"):
        _pad.typewrite = _make_typewrite()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# App allowlist — ONLY these apps can be launched via hardcoded list
# Key: normalised name(s), Value: executable command
# ---------------------------------------------------------------------------

APP_ALLOWLIST = {
    "notepad": "notepad.exe",
    "note pad": "notepad.exe",
    "node pad": "notepad.exe",
    "node": "notepad.exe",
    "notes": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "paint": "mspaint.exe",
    "task manager": "taskmgr.exe",
    "vs code": "code.exe",
    "vscode": "code.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powershell": "powershell.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "vlc": "vlc.exe",
    "spotify": "spotify.exe",
}

# Shell metacharacters banned from type_text
_SHELL_METACHARACTERS = set("&|;`$()<>")

# Max characters allowed for type_text
_TYPE_TEXT_MAX_LEN = 500


def _get_screenshots_dir() -> Path:
    from app.core.config import settings
    path = settings.DATA_DIR / "screenshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _open_app(params: dict) -> dict:
    raw_app = params.get("app", "").strip()
    norm_app = normalise(raw_app)

    # Step 1: Check hardcoded allowlist first
    exe = APP_ALLOWLIST.get(norm_app)

    if exe:
        try:
            if exe.startswith("shell:"):
                os.startfile(exe)
            else:
                subprocess.Popen([exe], shell=False)
            return {
                "success": True,
                "action": "open_app",
                "message": f"Opened {raw_app}",
                "data": {"exe": exe},
            }
        except FileNotFoundError:
            return {
                "success": False,
                "action": "open_app",
                "message": f"{exe} not found — is it installed?",
                "data": {},
            }
        except Exception as e:
            return {
                "success": False,
                "action": "open_app",
                "message": f"Failed to open {exe}: {e}",
                "data": {},
            }

    # Step 2: Not in allowlist — try dynamic app index
    try:
        from app.services.app_indexer_service import find_app
        indexed_path = find_app(raw_app)
        if indexed_path:
            os.startfile(indexed_path)
            return {
                "success": True,
                "action": "open_app",
                "message": f"Opened {raw_app}",
                "data": {"path": indexed_path},
            }
    except Exception as e:
        return {
            "success": False,
            "action": "open_app",
            "message": f"Found {raw_app} but failed to open: {e}",
            "data": {},
        }

    # Step 3: Neither allowlist nor index found it
    return {
        "success": False,
        "action": "open_app",
        "message": f"'{raw_app}' not found in allowlist or app index. Try saying the exact app name.",
        "data": {},
    }


def _lock_pc(params: dict) -> dict:
    try:
        result = ctypes.windll.user32.LockWorkStation()
        if result == 0:
            return {
                "success": False,
                "action": "lock_pc",
                "message": "LockWorkStation() failed — check permissions",
                "data": {},
            }
        return {
            "success": True,
            "action": "lock_pc",
            "message": "PC locked",
            "data": {},
        }
    except Exception as e:
        return {
            "success": False,
            "action": "lock_pc",
            "message": f"Lock failed: {e}",
            "data": {},
        }


def _take_screenshot(params: dict) -> dict:
    try:
        from PIL import ImageGrab
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        save_path = _get_screenshots_dir() / filename
        img = ImageGrab.grab()
        img.save(str(save_path))
        return {
            "success": True,
            "action": "take_screenshot",
            "message": f"Screenshot saved to {save_path}",
            "data": {"path": str(save_path)},
        }
    except Exception as e:
        return {
            "success": False,
            "action": "take_screenshot",
            "message": f"Screenshot failed: {e}",
            "data": {},
        }


def _type_text(params: dict) -> dict:
    text = params.get("text", "").strip()

    if len(text) > _TYPE_TEXT_MAX_LEN:
        return {
            "success": False,
            "action": "type_text",
            "message": f"Text too long ({len(text)} chars). Max is {_TYPE_TEXT_MAX_LEN}.",
            "data": {},
        }

    banned = [c for c in text if c in _SHELL_METACHARACTERS]
    if banned:
        return {
            "success": False,
            "action": "type_text",
            "message": f"Text contains banned characters: {set(banned)}",
            "data": {},
        }

    try:
        import pyauto_desktop
        sleep(0.5)
        pyauto_desktop.typewrite(text)
        return {
            "success": True,
            "action": "type_text",
            "message": f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}",
            "data": {"text": text},
        }
    except Exception as e:
        return {
            "success": False,
            "action": "type_text",
            "message": f"Typing failed: {e}",
            "data": {},
        }


def _web_search(params: dict) -> dict:
    query = params.get("query", "").strip()
    if not query:
        return {
            "success": False,
            "action": "web_search",
            "message": "No search query provided",
            "data": {},
        }
    import urllib.parse
    url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
    try:
        webbrowser.open(url)
        return {
            "success": True,
            "action": "web_search",
            "message": f"Searching for: {query}",
            "data": {"query": query, "url": url},
        }
    except Exception as e:
        return {
            "success": False,
            "action": "web_search",
            "message": f"Web search failed: {e}",
            "data": {},
        }


def _unknown(params: dict) -> dict:
    return {
        "success": False,
        "action": "unknown",
        "message": f"No action taken for: {params.get('raw', 'unknown command')}",
        "data": {},
    }


def _file_operation(params: dict) -> dict:
    """Route file operation sub-actions to file_service."""
    from app.services.file_service import (
        create_file, open_file, search_files, save_text
    )
    operation = params.get("operation", "").lower()
    if operation == "create":
        return {**create_file(
            params.get("name", "new_file"),
            params.get("content", ""),
            params.get("location", "desktop"),
        ), "action": "file_operation"}
    elif operation == "open":
        return {**open_file(params.get("path", "")),
                "action": "file_operation"}
    elif operation == "search":
        result = search_files(params.get("query", ""))
        if result.get("results"):
            print(f"\n[Files Found]\n" +
                  "\n".join(result["results"]) + "\n")
        return {**result, "action": "file_operation"}
    elif operation == "save":
        return {**save_text(
            params.get("text", ""),
            params.get("filename", "vasuki_output"),
            params.get("location", "desktop"),
        ), "action": "file_operation"}
    return {
        "success": False,
        "action": "file_operation",
        "message": f"Unknown file operation: {operation}",
        "data": {},
    }


def _answer_question(params: dict) -> dict:
    """Ask llama3.2 locally and return the answer. Fully offline."""
    question = params.get("question", "").strip()
    if not question:
        return {
            "success": False,
            "action": "answer_question",
            "message": "No question provided",
            "data": {},
        }
    try:
        import ollama
        response = ollama.chat(
            model="llama3.2:latest",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Vasuki, a helpful voice assistant. "
                        "Answer the user's question in 2-4 sentences. "
                        "No bullet points, no markdown, no headers — plain spoken language only. "
                        "Be helpful and complete but keep it concise enough to speak aloud."
                    ),
                },
                {"role": "user", "content": question},
            ],
        )
        answer = response["message"]["content"].strip()
        return {
            "success": True,
            "action": "answer_question",
            "message": answer,
            "data": {"question": question, "answer": answer},
        }
    except Exception as e:
        fallback = "I couldn't connect to my reasoning engine right now. Please try again."
        return {
            "success": False,
            "action": "answer_question",
            "message": fallback,
            "data": {},
        }


# ---------------------------------------------------------------------------
# Dispatch table + public API
# ---------------------------------------------------------------------------

_DISPATCH = {
    "open_app": _open_app,
    "lock_pc": _lock_pc,
    "take_screenshot": _take_screenshot,
    "type_text": _type_text,
    "web_search": _web_search,
    "answer_question": _answer_question,
    "file_operation": _file_operation,
    "unknown": _unknown,
}


def execute(intent: dict) -> dict:
    """
    Main entry point. Receives a Phase 4 intent dict and executes the action.
    Always returns a valid result dict — never raises.
    """
    try:
        action = intent.get("action", "unknown")
        params = intent.get("params") or {}

        handler = _DISPATCH.get(action)
        if handler is None:
            return {
                "success": False,
                "action": action,
                "message": f"Action not supported: {action}",
                "data": {},
            }

        try:
            return handler(params)
        except Exception as e:
            return {
                "success": False,
                "action": action,
                "message": f"Executor error: {e}",
                "data": {},
            }
    except Exception as e:
        return {
            "success": False,
            "action": "unknown",
            "message": f"Executor fatal error: {e}",
            "data": {},
        }