"""Environment configuration. All secrets are read server-side only."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
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
    documents_dir: Path = BACKEND_DIR / "data" / "documents"

    operator_username: str = "operator"
    operator_password: str = "repairflow-demo"
    # Toggle, not a removal: flip back to True (the safe default for anyone
    # else running this) before any live/public demo. False just makes
    # require_operator accept every request with no Authorization header.
    # Default OFF since 2026-09-21 (owner decision): this is a localhost
    # prototype and operator sign-in was removed from the UI entirely. It
    # remains a switch rather than a deletion so the capability survives if
    # this is ever exposed -- but the SPA no longer has a login form, so
    # turning it on makes every API call 401 until one is reintroduced.
    # See docs/26 and frontend-fixi/src/lib/auth-context.ts.
    operator_auth_enabled: bool = False

    # Gemini / Pydantic AI
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.7-flash"

    # ElevenLabs
    elevenlabs_api_key: str | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_webhook_secret: str | None = None
    elevenlabs_tool_secret: str | None = None
    elevenlabs_phone_number_id: str | None = None

    # Autonomous outbound calling (CLAUDE.md: "Live calls require allowlisted
    # test recipients and a documented enable switch"). Both default closed;
    # the coordinator can PROPOSE contacting the tenant regardless, but
    # nothing dials a real phone unless both are set.
    outbound_calls_enabled: bool = False
    outbound_call_allowlist: list[str] = Field(default_factory=list)

    # Earliest day offset MockBookingConnector generates slots at (docs/10).
    # Default 2 (unchanged, "believable" scheduling). For a compressed demo
    # timeline this can be lowered -- but never to 0: a same-day slot's
    # expires_at equals its start_at, so a slot generated after that hour
    # has already expired the instant it's created (see booking.py).
    demo_slot_offset_days: int = 2

    # Largest single upload accepted by the documents endpoint. Bounded
    # because the whole body is buffered to hash and size it before it is
    # written; an unbounded upload is a trivial memory exhaustion.
    max_document_bytes: int = 25 * 1024 * 1024

    # Tavily
    tavily_api_key: str | None = None

    # Public callback base (HTTPS tunnel) used for provider-facing URLs
    public_base_url: str = "http://localhost:8000"

    # Both dev ports. 5174 is what `npm run dev` in frontend-fixi actually
    # binds (vite.config.ts) and what the README tells you to open; 5173 is
    # the older `frontend/` app. Shipping only 5173 meant a fresh clone
    # followed the documented steps and got CORS failures from the only
    # frontend that is actually served -- the local .env had been fixed by
    # hand, so the breakage was invisible on this machine.
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:5174"]
    )
    # Escape hatch for the one legitimate wildcard case: a deployment that
    # genuinely wants an open, *credential-free* API. It drops credentials
    # rather than keeping them, because the dangerous combination is
    # precisely wildcard + credentials.
    cors_allow_credentials: bool = True

    @model_validator(mode="after")
    def _reject_wildcard_origin_with_credentials(self) -> "Settings":
        """`allow_origins=["*"]` with `allow_credentials=True` is not the
        harmless-looking dev convenience it reads as. Starlette treats a
        wildcard as "echo whatever Origin the request carried", so with
        credentials on, *any* site a signed-in operator visits can call
        this API with their session and read the response. The browser
        does not save you here -- echoing the origin is what makes it
        legal.

        Refuse at construction, so a bad CORS_ALLOW_ORIGINS fails the
        process loudly on boot instead of quietly widening access. The
        wildcard stays available for a genuinely open API, but only with
        CORS_ALLOW_CREDENTIALS=false, because the dangerous thing is the
        combination and not either half.
        """
        if "*" in self.cors_allow_origins and self.cors_allow_credentials:
            raise ValueError(
                "CORS_ALLOW_ORIGINS contains '*' while CORS_ALLOW_CREDENTIALS "
                "is true: that lets any origin call this API as the signed-in "
                "operator. List origins explicitly, or set "
                "CORS_ALLOW_CREDENTIALS=false to opt into an open, "
                "credential-free API."
            )
        return self

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
        self.documents_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
