"""
app/services/sensitive_filter_service.py
Detects and blocks harmful, sensitive, or dangerous content before any
command reaches the executor.

CONTENT POLICY — not a permission check. Even a verified user cannot ask
Vasuki to process content in these categories.

Categories:
- Indian PII: Aadhaar (keyword + digit formats), PAN card
- Financial: credit/debit card numbers, CVV, OTP
- Credentials: passwords, passphrases
- Prompt injection: attempts to override Vasuki's instructions
- Social engineering: impersonation, forgery attempts
- Dangerous commands: destructive OS commands
- Adult content: pornography, explicit material, nudity
- Abusive language: profanity, slurs (Hindi + English)

NOTE: Medical terms are intentionally NOT filtered — Vasuki should be
able to help users with health-related questions and care. The user's
right to get health information from their own local assistant is valid
and privacy-safe since everything stays on-device.

Audit behaviour: logs CATEGORY only, never the actual sensitive content.
"""
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_PATTERNS = [
    # -- Indian PII ----------------------------------------------------------
    (
        "aadhaar",
        re.compile(
            # Keyword match — catches voice commands like "type my Aadhaar"
            # regardless of how Whisper renders the digits
            r"\b(?:aadhaar|adhaar|aadhar|adhar)\b"
            # Standard grouped format: 1234 5678 9012 or 1234-5678-9012
            r"|\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"
            # Whisper digit-by-digit format: 1 2 3 4 5 6 7 8 9 0 1 2
            r"|\b(?:\d[\s]){11}\d\b",
            re.IGNORECASE,
        ),
    ),
    (
        "pan",
        re.compile(
            r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
        ),
    ),

    # -- Financial -----------------------------------------------------------
    (
        "credit_card",
        re.compile(
            r"\b\d{13,19}\b"
        ),
    ),
    (
        "cvv",
        re.compile(
            r"(?:cvv|security\s+code|card\s+code|cvc)[\s\S]{0,20}\b\d{3,4}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "otp",
        re.compile(
            r"(?:otp|one[\s\-]time|verification\s+code|auth\s+code)"
            r"[\s\S]{0,20}\b\d{4,6}\b",
            re.IGNORECASE,
        ),
    ),

    # -- Credentials ---------------------------------------------------------
    (
        "password",
        re.compile(
            r"\b(?:password|passwd|passphrase|secret\s+key)\b",
            re.IGNORECASE,
        ),
    ),

    # -- Prompt injection ----------------------------------------------------
    # Attempts to override Vasuki's core instructions via voice
    (
        "prompt_injection",
        re.compile(
            r"\b(?:"
            r"ignore\s+(?:(?:my|all|the)\s+)?(?:previous|prior|earlier|your)\s+instructions?"
            r"|forget\s+(?:everything|your\s+instructions?|what\s+you\s+know)"
            r"|you\s+are\s+now\s+(?:a|an)\b"
            r"|disregard\s+your"
            r"|override\s+your"
            r"|your\s+new\s+(?:instructions?|rules?|role)\s+are"
            r"|from\s+now\s+on\s+you\s+are"
            r"|new\s+persona"
            r"|jailbreak"
            r"|dan\s+mode"
            r"|developer\s+mode"
            r")\b",
            re.IGNORECASE,
        ),
    ),

    # -- Social engineering --------------------------------------------------
    # Impersonation and forgery attempts
    (
        "social_engineering",
        re.compile(
            r"\b(?:"
            r"impersonat(?:e|ing)"
            r"|pretend\s+to\s+be\s+(?:my\s+)?(?:boss|manager|teacher|parent|friend|bank|police|government)"
            r"|write\s+as\s+if\s+you\s+(?:are|were)"
            r"|type\s+(?:an?\s+)?(?:email|message|letter)\s+(?:pretending|as\s+if|claiming)"
            r"|forge\s+(?:an?\s+)?(?:email|letter|document|signature)"
            r"|act\s+as\s+(?:my\s+)?(?:boss|manager|teacher|bank|police)"
            r")\b",
            re.IGNORECASE,
        ),
    ),

    # -- Dangerous destructive commands --------------------------------------
    # OS-level destruction beyond what metacharacter filter catches
    (
        "dangerous_command",
        re.compile(
            r"\b(?:"
            r"delete\s+everything"
            r"|delete\s+all\s+(?:files|data|folders)"
            r"|format\s+(?:the\s+)?(?:drive|disk|hard\s+drive|c\s+drive)"
            r"|wipe\s+(?:the\s+)?(?:drive|disk|everything|all\s+data)"
            r"|erase\s+(?:all|everything|the\s+(?:drive|disk))"
            r"|rm\s+-rf"
            r"|del\s+/f\s+/s"
            r"|uninstall\s+everything"
            r")\b",
            re.IGNORECASE,
        ),
    ),

    # -- Adult content -------------------------------------------------------
    (
        "adult_content",
        re.compile(
            r"\b(?:"
            r"porn(?:ography|ographic)?"
            r"|explicit\s+(?:content|video|image|material)"
            r"|nudity|nude\s+(?:images?|videos?|photos?|pic(?:ture)?s?|content)"
            r"|sexual\s+(?:content|material|videos?)"
            r"|xxx"
            r"|adult\s+content"
            r"|erotic(?:a)?"
            r"|hentai"
            r"|obscene\s+(?:content|material)"
            r")\b",
            re.IGNORECASE,
        ),
    ),

    # -- Abusive language ----------------------------------------------------
    # English profanity + common Hindi abusive terms
    # Applied to commands — not blocking discussion/search of these topics
    (
        "abusive_language",
        re.compile(
            r"\b(?:"
            r"fuck(?:ing|er|ed)?"
            r"|motherfuck(?:ing|er)?"
            r"|son\s+of\s+a\s+bitch"
            r"|bitch(?:es)?"
            r"|bastard"
            r"|asshole"
            r"|cunt"
            r"|cock\s*sucker"
            # Hindi abusive terms
            r"|bhenchod|bhen\s*chod"
            r"|madarchod|madar\s*chod"
            r"|chutiya|chut(?:iye)?"
            r"|gaandu|gandu"
            r"|randi"
            r"|harami"
            r"|saala\s+kutta"
            r"|bhosdike"
            r")\b",
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_sensitive(text: str) -> dict:
    """
    Checks text for sensitive, harmful, or dangerous content patterns.

    Returns:
        {
            "blocked": bool,
            "reason": str,      # human-readable, safe to print
            "category": str     # category name, or "" if not blocked
        }

    IMPORTANT: the returned dict never contains the actual sensitive content.
    """
    for category, pattern in _PATTERNS:
        if pattern.search(text):
            category_display = category.replace("_", " ").title()
            return {
                "blocked": True,
                "reason": f"{category_display} detected. "
                          f"Vasuki cannot process this command.",
                "category": category,
            }
    return {
        "blocked": False,
        "reason": "",
        "category": "",
    }


def is_safe(text: str) -> bool:
    """Convenience wrapper — returns True if text is safe to process."""
    return not check_sensitive(text)["blocked"]