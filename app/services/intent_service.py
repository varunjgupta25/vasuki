"""
app/services/intent_service.py
Three-tier intent parsing cascade: regex → SQLite cache → Ollama.

Intent schema (frozen — Phase 5 depends on this exact shape):
    {
        "action": str,       # SUPPORTED_ACTIONS
        "params": dict,
        "confidence": float,
        "source": str        # "regex" | "cache" | "ollama" | "fallback"
    }

Cascade rules:
1. Normalise text (lowercase, strip punctuation, collapse whitespace)
2. Try regex patterns — O(1), zero latency
3. Try SQLite cache — avoids re-querying Ollama for seen commands
4. Try Ollama (llama3.2) — local LLM, structured JSON output
5. Fallback: return unknown intent — never crash

Offline resilience: steps 1–3 work with no Ollama process running.
BANNED: glm-5.1:cloud — sovereignty violation, never use.
"""
import json
import re
import sqlite3
import threading
from typing import Optional

_cache_lock = threading.Lock()
_DB_PATH: Optional[str] = None


def _get_db_path() -> str:
    from app.core.config import settings
    return str(settings.SYSTEM_DB_PATH)


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Regex tier — data-driven patterns
# ---------------------------------------------------------------------------

# Each entry: (compiled_pattern, action, param_builder)
# param_builder receives the match object and returns the params dict.
_REGEX_RULES = [
    (
        re.compile(r"^(?:open|find|show)\s+(?:my\s+)?(?:file|document|folder)\s+(?:called?\s+|named\s+)?(.+)$"),
        "file_operation",
        lambda m: {"operation": "search", "query": m.group(1).strip()},
    ),
    (
        re.compile(r"^(?:now\s+|please\s+|can\s+you\s+)?(?:open|launch|start)\s+(?:the\s+)?(.+)$"),
        "open_app",
        lambda m: {"app": m.group(1).strip()},
    ),
    (
        re.compile(r"^(?:lock|lock the pc|lock the computer|lock screen)$"),
        "lock_pc",
        lambda m: {},
    ),
    (
        re.compile(r"^(?:take a screenshot|screenshot|capture screen|take screenshot)$"),
        "take_screenshot",
        lambda m: {},
    ),
    (
        re.compile(r"^type(?:\s+(?:out|in))?\s+(.+)$"),
        "type_text",
        lambda m: {"text": m.group(1).strip()},
    ),
    (
        re.compile(r"^(?:search(?:\s+for)?|google|look up)\s+(.+)$"),
        "web_search",
        lambda m: {"query": m.group(1).strip()},
    ),
    (
        re.compile(
            r"^(?:what|who|where|when|why|how|tell\s+me|explain|define)\b.+$"
        ),
        "answer_question",
        lambda m: {"question": m.string.strip()},
    ),
    
]


def _try_regex(text: str) -> Optional[dict]:
    norm = normalise(text)
    for pattern, action, param_builder in _REGEX_RULES:
        m = pattern.match(norm)
        if m:
            return {
                "action": action,
                "params": param_builder(m),
                "confidence": 1.0,
                "source": "regex",
            }
    return None


# ---------------------------------------------------------------------------
# Cache tier — SQLite memoisation
# ---------------------------------------------------------------------------

def _ensure_cache_table() -> None:
    with _cache_lock:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            """CREATE TABLE IF NOT EXISTS intent_cache (
                norm_text TEXT PRIMARY KEY,
                action    TEXT NOT NULL,
                params    TEXT NOT NULL,
                confidence REAL NOT NULL
            )"""
        )
        conn.commit()
        conn.close()


def _cache_get(norm_text: str) -> Optional[dict]:
    with _cache_lock:
        try:
            conn = sqlite3.connect(_get_db_path())
            row = conn.execute(
                "SELECT action, params, confidence FROM intent_cache WHERE norm_text=?",
                (norm_text,),
            ).fetchone()
            conn.close()
            if row:
                return {
                    "action": row[0],
                    "params": json.loads(row[1]),
                    "confidence": row[2],
                    "source": "cache",
                }
        except Exception:
            pass
    return None


def _cache_set(norm_text: str, intent: dict) -> None:
    with _cache_lock:
        try:
            conn = sqlite3.connect(_get_db_path())
            conn.execute(
                """INSERT OR REPLACE INTO intent_cache
                   (norm_text, action, params, confidence)
                   VALUES (?, ?, ?, ?)""",
                (
                    normalise(norm_text),
                    intent["action"],
                    json.dumps(intent["params"]),
                    intent["confidence"],
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


def _try_cache(text: str) -> Optional[dict]:
    return _cache_get(normalise(text))


# ---------------------------------------------------------------------------
# Ollama tier — local LLM with hardened JSON parsing
# ---------------------------------------------------------------------------

_OLLAMA_SYSTEM = """You are an intent parser for a voice assistant. 
Given a voice command, return ONLY a JSON object with this exact schema:
{"action": str, "params": {}, "confidence": float}

Supported actions and their params:
- open_app: {"app": "<app name>"}
- lock_pc: {}
- take_screenshot: {}
- type_text: {"text": "<text to type>"}
- web_search: {"query": "<search query>"}
- answer_question: {"question": "<question text>"}  ← answered locally by llama3.2
- unknown: {"raw": "<original command>"}

Rules:
- Return ONLY the JSON object, no markdown, no explanation
- confidence is 0.0-1.0
- Use "unknown" if the command doesn't match any action"""


def _parse_ollama_response(raw: str) -> Optional[dict]:
    """Strip markdown fences and parse JSON. Returns None on any error."""
    try:
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        if "action" not in data or "params" not in data:
            return None
        return {
            "action": str(data.get("action", "unknown")),
            "params": dict(data.get("params", {})),
            "confidence": float(data.get("confidence", 0.5)),
            "source": "ollama",
        }
    except Exception:
        return None


def _try_ollama(text: str) -> Optional[dict]:
    try:
        import ollama
        from app.core.config import settings
        response = ollama.chat(
            model=settings.INTENT_MODEL,  # ONLY local model — glm-5.1:cloud is banned
            messages=[
                {"role": "system", "content": _OLLAMA_SYSTEM},
                {"role": "user", "content": text},
            ],
        )
        raw = response["message"]["content"]
        return _parse_ollama_response(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback(text: str) -> dict:
    return {
        "action": "unknown",
        "params": {"raw": text},
        "confidence": 0.0,
        "source": "fallback",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prewarm_ollama() -> None:
    """Send a silent dummy request to Ollama on startup to eliminate
    cold-start latency (2-3 seconds on Windows) for the first real command."""
    try:
        import ollama
        from app.core.config import settings
        ollama.chat(
            model=settings.INTENT_MODEL,
            messages=[{"role": "user", "content": "ping"}],
        )
    except Exception:
        pass  # Ollama not running — that's fine, cascade handles it


def parse_intent(text: str) -> dict:
    """
    Main entry point. Maps a transcribed command to a structured intent.
    Always returns a valid intent dict — never raises.
    """
    _ensure_cache_table()

    intent = _try_regex(text)
    if intent:
        return intent

    intent = _try_cache(text)
    if intent:
        return intent

    intent = _try_ollama(text)
    if intent:
        _cache_set(text, intent)
        return intent

    return _fallback(text)
