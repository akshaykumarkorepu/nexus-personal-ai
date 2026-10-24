"""Backend configuration, read from environment variables (and an optional backend/.env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- AI provider -------------------------------------------------------
    # "auto": Anthropic when credentials exist, otherwise report "not configured".
    # "ollama": a local model served by Ollama; no API key, no usage cost.
    # "demo": explicitly labeled offline echo mode; never calls a model or runs tools.
    provider: Literal["auto", "anthropic", "ollama", "demo"] = Field("auto", alias="NEXUS_PROVIDER")
    anthropic_api_key: SecretStr | None = Field(None, alias="ANTHROPIC_API_KEY")
    anthropic_auth_token: SecretStr | None = Field(None, alias="ANTHROPIC_AUTH_TOKEN")
    anthropic_base_url: str | None = Field(None, alias="ANTHROPIC_BASE_URL")
    model: str = Field("claude-opus-5-5", alias="NEXUS_MODEL")
    effort: Effort = Field("medium", alias="NEXUS_EFFORT")
    max_tokens: int = Field(32000, ge=1024, le=128000, alias="NEXUS_MAX_TOKENS")
    # Server-side refusal fallback: if the model's safety classifiers decline a
    # request, the API re-runs it on Anthropic's recommended fallback model.
    refusal_fallback: bool = Field(True, alias="NEXUS_REFUSAL_FALLBACK")
    request_timeout_seconds: float = Field(600.0, gt=0, alias="NEXUS_REQUEST_TIMEOUT_SECONDS")

    # --- Ollama (local models) -----------------------------------------------
    ollama_url: str = Field("http://127.0.0.1:11434", alias="NEXUS_OLLAMA_URL")
    ollama_model: str = Field("qwen3:4b", min_length=1, alias="NEXUS_OLLAMA_MODEL")
    ollama_num_ctx: int = Field(16384, ge=2048, le=262144, alias="NEXUS_OLLAMA_NUM_CTX")

    # --- Storage -------------------------------------------------------------
    db_path: Path = Field(BACKEND_DIR / "data" / "nexus.db", alias="NEXUS_DB_PATH")

    # --- HTTP ----------------------------------------------------------------
    cors_origins: str = Field("http://localhost:3000", alias="NEXUS_CORS_ORIGINS")

    # --- Tools ---------------------------------------------------------------
    # Comma-separated absolute directories the file tools may read. Empty = none.
    allowed_dirs: str = Field("", alias="NEXUS_ALLOWED_DIRS")
    max_tool_iterations: int = Field(8, ge=1, le=32, alias="NEXUS_MAX_TOOL_ITERATIONS")
    tool_timeout_seconds: float = Field(10.0, gt=0, le=120, alias="NEXUS_TOOL_TIMEOUT_SECONDS")
    max_read_chars: int = Field(60_000, ge=1_000, le=500_000, alias="NEXUS_MAX_READ_CHARS")
    max_file_bytes: int = Field(25 * 1024 * 1024, ge=1024, alias="NEXUS_MAX_FILE_BYTES")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_dir_list(self) -> list[Path]:
        """Approved roots, resolved. Non-existent or relative entries are dropped."""
        roots: list[Path] = []
        for raw in self.allowed_dirs.split(","):
            raw = raw.strip()
            if not raw:
                continue
            p = Path(raw).expanduser()
            if not p.is_absolute():
                continue
            try:
                resolved = p.resolve(strict=True)
            except OSError:
                continue
            if resolved.is_dir() and resolved not in roots:
                roots.append(resolved)
        return roots

    @property
    def has_anthropic_credentials(self) -> bool:
        return bool(
            (self.anthropic_api_key and self.anthropic_api_key.get_secret_value())
            or (self.anthropic_auth_token and self.anthropic_auth_token.get_secret_value())
        )

    @property
    def resolved_provider(self) -> Literal["anthropic", "ollama", "demo", "unconfigured"]:
        if self.provider in ("demo", "ollama"):
            return self.provider
        if self.has_anthropic_credentials:
            return "anthropic"
        return "unconfigured"

    @property
    def active_model(self) -> str:
        return self.ollama_model if self.resolved_provider == "ollama" else self.model


@lru_cache
def get_settings() -> Settings:
    return Settings()
