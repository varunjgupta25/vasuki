"""
app/core/config.py
Central settings for Vasuki.

No hardcoded user identity anywhere in this file. Vasuki is designed to
support multiple enrolled users from day one — every path that touches
a specific user must be parameterized by user_id, never assumed.
"""
import ctypes
import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


def _detect_total_ram_gb() -> float:
    """Detect total physical RAM in gigabytes.

    Uses Windows GlobalMemoryStatusEx via ctypes.
    Falls back to sysconf or a safe default (8.0 GB) on non-Windows / error.
    """
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        pass

    try:
        return (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3)
    except Exception:
        pass

    return 8.0


def _resolve_intent_model() -> str:
    """Resolve local intent model based on available system RAM.

    - < 8GB RAM: phi4-mini
    - >= 8GB RAM: qwen2.5:7b
    """
    ram_gb = _detect_total_ram_gb()
    if ram_gb < 8.0:
        return "phi4-mini"
    return "qwen2.5:7b"


class Settings(BaseSettings):
    # -- Paths ------------------------------------------------------------
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "var" / "data"
    LOG_DIR: Path = PROJECT_ROOT / "var" / "logs"
    VOICE_PROFILE_DIR: Path = DATA_DIR / "voice_profiles"  # one *.npy per user_id
    INTRUDER_PHOTO_DIR: Path = DATA_DIR / "intruder_photos"

    # -- Database -----------------------------------------------------------
    SYSTEM_DB_PATH: Path = DATA_DIR / "vasuki.db"
    SYSTEM_DB_URL: str = f"sqlite:///{SYSTEM_DB_PATH}"
    SYSTEM_DB_ASYNC_URL: str = f"sqlite+aiosqlite:///{SYSTEM_DB_PATH}"

    # -- Models ---------------------------------------------------------------
    INTENT_MODEL: str = Field(default_factory=_resolve_intent_model)  # Single source of truth — never hardcode elsewhere

    # -- Server ---------------------------------------------------------------
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    class Config:
        env_file = ".env"

    def ensure_dirs(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.VOICE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self.INTRUDER_PHOTO_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
