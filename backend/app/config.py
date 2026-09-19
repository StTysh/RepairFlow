"""Environment configuration. All secrets are read server-side only."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    data_dir: Path = BACKEND_DIR / "data"
    database_path: Path = BACKEND_DIR / "data" / "repairflow.db"
    recordings_dir: Path = BACKEND_DIR / "data" / "recordings"

    operator_username: str = "operator"
    operator_password: str = "repairflow-demo"

    # Gemini / Pydantic AI
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.7-flash"

    # ElevenLabs
    elevenlabs_api_key: str | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_webhook_secret: str | None = None
    elevenlabs_tool_secret: str | None = None

    # Tavily
    tavily_api_key: str | None = None

    # Public callback base (HTTPS tunnel) used for provider-facing URLs
    public_base_url: str = "http://localhost:8000"

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def gemini_live(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def elevenlabs_live(self) -> bool:
        return bool(self.elevenlabs_api_key and self.elevenlabs_agent_id)

    @property
    def tavily_live(self) -> bool:
        return bool(self.tavily_api_key)

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
