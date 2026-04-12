"""config/settings.py — Centralised application settings via pydantic-settings.

Phase 1.8: Moves secrets out of .streamlit/secrets.toml into environment
variables, validated at startup so bad configuration fails fast.

Usage:
    from config.settings import settings
    key = settings.anthropic_api_key
"""

import os
from typing import Optional

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field, field_validator

    class Settings(BaseSettings):
        """Application settings — sourced from environment variables / .env file."""

        # ── Required ─────────────────────────────────────────
        anthropic_api_key: str = Field(
            default="",
            validation_alias="ANTHROPIC_API_KEY",
            description="Anthropic API key (sk-ant-...)",
        )

        # ── Optional auth (replaces .streamlit/secrets.toml hardcoded creds) ──
        auth_username: Optional[str] = Field(
            default=None,
            validation_alias="AUTH_USERNAME",
            description="Streamlit / API auth username. Set to enable password protection.",
        )
        auth_password: Optional[str] = Field(
            default=None,
            validation_alias="AUTH_PASSWORD",
            description="Streamlit / API auth password.",
        )

        # ── API Bearer token for FastAPI ──────────────────────
        api_bearer_token: Optional[str] = Field(
            default=None,
            validation_alias="API_BEARER_TOKEN",
            description="Optional static Bearer token to protect /api/* endpoints.",
        )

        # ── Server ────────────────────────────────────────────
        host: str = Field(default="0.0.0.0", validation_alias="HOST")
        port: int = Field(default=8000, validation_alias="PORT")
        log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
        log_json: bool = Field(default=True, validation_alias="LOG_JSON")

        # ── Analysis defaults ─────────────────────────────────
        default_mode: int = Field(default=4, validation_alias="DEFAULT_MODE")
        default_max_rounds: int = Field(default=3, validation_alias="DEFAULT_MAX_ROUNDS")
        default_domain_model: str = Field(
            default="sonnet", validation_alias="DEFAULT_DOMAIN_MODEL"
        )

        @field_validator("anthropic_api_key")
        @classmethod
        def _check_api_key(cls, v: str) -> str:
            if v and not v.startswith("sk-ant-"):
                raise ValueError("ANTHROPIC_API_KEY must start with 'sk-ant-'")
            return v

        model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

except ImportError:
    # pydantic-settings not installed — fall back to plain os.getenv
    class Settings:  # type: ignore[no-redef]
        """Fallback settings when pydantic-settings is not installed."""

        @property
        def anthropic_api_key(self) -> str:
            return os.getenv("ANTHROPIC_API_KEY", "")

        @property
        def auth_username(self) -> Optional[str]:
            return os.getenv("AUTH_USERNAME")

        @property
        def auth_password(self) -> Optional[str]:
            return os.getenv("AUTH_PASSWORD")

        @property
        def api_bearer_token(self) -> Optional[str]:
            return os.getenv("API_BEARER_TOKEN")

        @property
        def host(self) -> str:
            return os.getenv("HOST", "0.0.0.0")

        @property
        def port(self) -> int:
            return int(os.getenv("PORT", "8000"))

        @property
        def log_level(self) -> str:
            return os.getenv("LOG_LEVEL", "INFO")

        @property
        def log_json(self) -> bool:
            return os.getenv("LOG_JSON", "true").lower() in ("true", "1", "yes")

        @property
        def default_mode(self) -> int:
            return int(os.getenv("DEFAULT_MODE", "4"))

        @property
        def default_max_rounds(self) -> int:
            return int(os.getenv("DEFAULT_MAX_ROUNDS", "3"))

        @property
        def default_domain_model(self) -> str:
            return os.getenv("DEFAULT_DOMAIN_MODEL", "sonnet")


# Singleton — import and use `settings` directly
try:
    settings = Settings()
except Exception:
    settings = Settings()  # type: ignore[assignment]
