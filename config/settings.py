"""
Centralized configuration — loads all environment variables from .env file.

Usage:
    from config.settings import settings
    llm_key = settings.openai_api_key
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


@dataclass(frozen=True)
class Settings:
    """Typed, immutable config object for the entire project."""

    # ---- OpenAI ----
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.2
    openai_max_tokens: int = 2048

    # ---- LangSmith ----
    langchain_tracing_v2: str = field(
        default_factory=lambda: os.getenv("LANGCHAIN_TRACING_V2", "false")
    )
    langchain_api_key: str = field(
        default_factory=lambda: os.getenv("LANGCHAIN_API_KEY", "")
    )
    langchain_project: str = field(
        default_factory=lambda: os.getenv("LANGCHAIN_PROJECT", "prior-auth-agent")
    )

    # ---- Supabase ----
    supabase_url: str = field(
        default_factory=lambda: os.getenv("SUPABASE_URL", "")
    )
    supabase_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_KEY", "")
    )

    # ---- Paths ----
    data_dir: Path = field(
        default_factory=lambda: _project_root / "data"
    )
    patients_file: Path = field(
        default_factory=lambda: _project_root / "data" / "patients.json"
    )

    # ---- Agent Tuning ----
    max_retries: int = 2
    hitl_enabled: bool = True

    # ---- Cost Rates (GPT-4o mini, per 1M tokens) ----
    input_cost_per_million: float = 0.15
    output_cost_per_million: float = 0.60

    @property
    def tracing_enabled(self) -> bool:
        return self.langchain_tracing_v2.lower() == "true" and bool(self.langchain_api_key)

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url) and bool(self.supabase_key)

    def validate(self) -> list[str]:
        """Return a list of missing-but-required config warnings."""
        warnings = []
        if not self.openai_api_key:
            warnings.append("OPENAI_API_KEY is not set — agents will fail.")
        return warnings


# Module-level singleton
settings = Settings()
