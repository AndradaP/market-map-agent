from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM
    # SecretStr, not str: this whole Settings object gets passed as an argument
    # to every @traceable-decorated llm.py/search.py function, and LangSmith's
    # tracing captures full function arguments -- a plain str field here means
    # the raw key gets uploaded to LangSmith in plaintext on every call (this
    # actually happened: found live in a trace, all three keys had to be
    # rotated). SecretStr reprs/serializes as '**********' unless code
    # explicitly calls .get_secret_value(), which only the real client
    # constructors below should ever do.
    anthropic_api_key: Optional[SecretStr] = None
    # Only needed for an org-level (unscoped) key on a multi-workspace account —
    # sent as the `anthropic-workspace-id` header. Leave blank for a
    # workspace-scoped key (the normal case).
    anthropic_workspace_id: Optional[str] = None
    anthropic_base_url: Optional[str] = None  # defaults to the real API
    anthropic_model_judgment: str = "claude-opus-5"
    anthropic_model_mechanical: str = "claude-sonnet-5"

    # Search / verification
    exa_api_key: Optional[SecretStr] = None

    # Observability
    langsmith_api_key: Optional[SecretStr] = None
    langsmith_project: str = "market-map-agent"

    # Persistence (run log + LangGraph checkpointer share this DB) -- a
    # connection string with an embedded password, same leak risk as the API
    # keys above.
    database_url: Optional[SecretStr] = None

    # Behaviour
    use_stubs: bool = True
    rescope_cap: int = 2

    # Per-layer company volume. Soft target = what Execute aims for; hard cap = the
    # ceiling that truncates AND emits a "layer too broad" warning.
    layer_company_soft_target: int = 12
    layer_company_hard_cap: int = 25

    # Execute pipeline (real path): how many companies to extract per layer, how
    # many Exa results per per-company corroboration search, and the parallelism
    # of those searches within a layer.
    layer_extract_cap: int = 15
    company_corroboration_results: int = 8
    company_corroboration_workers: int = 4

    # Rescope-note quality floor (chars) before the one free clarification round.
    rescope_min_note_chars: int = 15

    # Public-deploy cost guardrail: caps on new runs ("maps") per calendar day.
    # None = disabled (local dev / tests). The public deploy sets both --
    # per-IP so one stranger can't eat the whole day's budget, global as a
    # backstop against IP rotation. See backend/app/rate_limit.py.
    daily_run_limit_per_ip: Optional[int] = None
    daily_run_limit_global: Optional[int] = None
    # A shared secret only the owner knows, set once in their own browser's
    # localStorage (never checked into git or built into the public JS bundle)
    # -- a request carrying it skips the cap entirely. None = no bypass exists.
    rate_limit_bypass_token: Optional[SecretStr] = None

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
