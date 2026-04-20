"""Application configuration with environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _as_list(value: str | None, *, default: list[str]) -> list[str]:
    if value is None:
        return default
    items = [part.strip() for part in value.split(",")]
    clean = [item for item in items if item]
    return clean or default


def _parse_api_tokens(value: str | None) -> dict[str, str]:
    if value is None or not value.strip():
        return {
            "local-dev-api-key": "admin",
            "local-viewer-api-key": "viewer",
        }

    parsed: dict[str, str] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if ":" not in item:
            continue
        key, role = item.split(":", maxsplit=1)
        key = key.strip()
        role = role.strip().lower()
        if key and role:
            parsed[key] = role
    if not parsed:
        return {
            "local-dev-api-key": "admin",
            "local-viewer-api-key": "viewer",
        }
    return parsed


@dataclass(frozen=True)
class Settings:
    """Typed runtime settings."""

    app_env: str
    database_url: str
    cors_origins: list[str]
    require_api_auth: bool
    api_tokens: dict[str, str]
    api_rate_limit_max_requests: int
    api_rate_limit_window_sec: int
    sync_qc_mode: str
    gemini_api_key: str
    openai_api_key: str
    claude_api_key: str
    gemini_model: str
    openai_model: str
    claude_model: str
    ai_enabled_providers: list[str]
    ai_max_prompt_chars: int
    ai_max_image_b64_chars: int
    ai_max_tokens: int


def load_settings() -> Settings:
    """Build settings from process environment."""
    return Settings(
        app_env=os.environ.get("APP_ENV", "dev"),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///./app_local.db"),
        cors_origins=_as_list(
            os.environ.get("CORS_ORIGINS"),
            default=["http://127.0.0.1:5173", "http://localhost:5173"],
        ),
        require_api_auth=_as_bool(os.environ.get("REQUIRE_API_AUTH"), default=True),
        api_tokens=_parse_api_tokens(os.environ.get("API_TOKENS")),
        api_rate_limit_max_requests=_as_int(os.environ.get("API_RATE_LIMIT_MAX_REQUESTS"), default=60),
        api_rate_limit_window_sec=_as_int(os.environ.get("API_RATE_LIMIT_WINDOW_SEC"), default=60),
        sync_qc_mode=os.environ.get("EMOTIBIT_SYNC_QC_MODE", "lenient").strip().lower() or "lenient",
        gemini_api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        claude_api_key=os.environ.get("CLAUDE_API_KEY", "").strip(),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-1.5-pro").strip() or "gemini-1.5-pro",
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022").strip()
        or "claude-3-5-sonnet-20241022",
        ai_enabled_providers=_as_list(
            os.environ.get("AI_ENABLED_PROVIDERS"),
            default=["gemini", "openai", "claude"],
        ),
        ai_max_prompt_chars=_as_int(os.environ.get("AI_MAX_PROMPT_CHARS"), default=2000),
        ai_max_image_b64_chars=_as_int(os.environ.get("AI_MAX_IMAGE_B64_CHARS"), default=10_000_000),
        ai_max_tokens=_as_int(os.environ.get("AI_MAX_TOKENS"), default=800),
    )


settings = load_settings()

