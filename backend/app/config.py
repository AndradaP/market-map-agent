from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM
    anthropic_api_key: Optional[str] = None
    anthropic_model_judgment: str = "claude-opus-5"
    anthropic_model_mechanical: str = "claude-sonnet-5"

    # Search / verification
    exa_api_key: Optional[str] = None

    # Observability
    langsmith_api_key: Optional[str] = None
    langsmith_project: str = "market-map-agent"

    # Persistence (run log + LangGraph checkpointer share this DB)
    database_url: Optional[str] = None

    # Behaviour
    use_stubs: bool = True
    rescope_cap: int = 2

    # Corroboration: tier-weighted score a company must clear to be "corroborated"
    # (tier1=2.0, tier2=1.5, tier3=1.0 per distinct independent source — see sources.py).
    corroboration_threshold: float = 3.0

    # Per-layer company volume. Soft target = what Execute aims for; hard cap = the
    # ceiling that truncates AND emits a "layer too broad" warning.
    layer_company_soft_target: int = 12
    layer_company_hard_cap: int = 25

    # Rescope-note quality floor (chars) before the one free clarification round.
    rescope_min_note_chars: int = 15

    @property
    def stubs_enabled(self) -> bool:
        """Deterministic offline mode: explicit opt-in, or any live key missing."""
        if self.use_stubs:
            return True
        return not (self.anthropic_api_key and self.exa_api_key)

    @property
    def checkpointer_backend(self) -> str:
        return "postgres" if self.database_url else "memory"


@lru_cache
def get_settings() -> Settings:
    return Settings()
