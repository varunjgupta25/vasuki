"""
app/core/config.py
Central settings for Vasuki.

No hardcoded user identity anywhere in this file. Vasuki is designed to
support multiple enrolled users from day one — every path that touches
a specific user must be parameterized by user_id, never assumed.
"""
from pathlib import Path
from pydantic_settings import BaseSettings


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
