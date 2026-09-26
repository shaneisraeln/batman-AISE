"""Central configuration for BATMAN.

Values are read from environment variables (and a local .env file if present).
Everything has a safe default so the system runs with zero external services.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:  # optional dependency; loaded if available
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    val = os.getenv(name)
    try:
        return float(val) if val is not None else default
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    try:
        return int(val) if val is not None else default
    except ValueError:
        return default


@dataclass
class RateLimitConfig:
    requests_per_minute: int = field(
        default_factory=lambda: _get_int("BATMAN_RL_RPM", 60)
    )
    burst: int = field(default_factory=lambda: _get_int("BATMAN_RL_BURST", 10))


@dataclass
class Settings:
    # General
    db_path: str = field(default_factory=lambda: os.getenv("BATMAN_DB_PATH", "batman.db"))
    mode: str = field(default_factory=lambda: os.getenv("BATMAN_MODE", "enforce"))
    log_level: str = field(default_factory=lambda: os.getenv("BATMAN_LOG_LEVEL", "INFO"))

    # LLM
    llm_provider: str = field(
        default_factory=lambda: os.getenv("BATMAN_LLM_PROVIDER", "stub")
    )
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    )
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    bedrock_model_id: str = field(
        default_factory=lambda: os.getenv(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
        )
    )

    # RAG / embeddings
    embeddings_backend: str = field(
        default_factory=lambda: os.getenv("BATMAN_EMBEDDINGS_BACKEND", "hashing")
    )
    sentence_transformers_model: str = field(
        default_factory=lambda: os.getenv(
            "SENTENCE_TRANSFORMERS_MODEL", "all-MiniLM-L6-v2"
        )
    )
    vector_store: str = field(
        default_factory=lambda: os.getenv("BATMAN_VECTOR_STORE", "memory")
    )
    rag_top_k: int = field(default_factory=lambda: _get_int("BATMAN_RAG_TOP_K", 4))

    # Detection thresholds (calibrate experimentally)
    anomaly_threshold: float = field(
        default_factory=lambda: _get_float("BATMAN_ANOMALY_THRESHOLD", 0.6)
    )
    extraction_threshold: float = field(
        default_factory=lambda: _get_float("BATMAN_EXTRACTION_THRESHOLD", 0.6)
    )

    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)

    def validate(self) -> None:
        if self.mode not in {"monitor", "enforce"}:
            raise ValueError(f"Invalid BATMAN_MODE: {self.mode!r} (monitor|enforce)")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.validate()
    return s
