"""Application configuration via Pydantic Settings.

All externally configurable values live here. Populate via environment
variables or a .env file at the project root.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    app_name: str = "Sales Agentic AI"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # ------------------------------------------------------------------
    # API / Security
    # ------------------------------------------------------------------
    secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING",
        description="JWT signing secret — MUST be overridden in production",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    # Comma-separated list of allowed CORS origins
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ------------------------------------------------------------------
    # Database — PostgreSQL
    # ------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/sales_ai",
        description="Async SQLAlchemy connection URL",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False  # flip to True to log SQL

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ------------------------------------------------------------------
    # Vector Store
    # ------------------------------------------------------------------
    vector_store: Literal["qdrant", "faiss"] = "qdrant"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "sales_ai_embeddings"

    # FAISS (local fallback)
    faiss_index_path: str = "./data/faiss_index"

    # ------------------------------------------------------------------
    # LLM Provider — switch between openai | grok | ollama | custom
    # ------------------------------------------------------------------
    llm_provider: Literal["openai", "grok", "ollama", "custom"] = "ollama"

    # --- xAI / Grok ---
    grok_api_key: str = Field(default="", description="xAI API key (format: xai-...)")
    grok_base_url: str = "https://api.x.ai/v1"
    grok_model: str = "grok-3-beta"   # or grok-2-1212, grok-beta

    # --- OpenAI (set llm_provider=openai to use) ---
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # --- Ollama (local, set llm_provider=ollama) ---
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3"
    ollama_api_key: str = "ollama"   # Ollama ignores this but SDK requires it

    # --- Custom / Any other OpenAI-compatible endpoint ---
    custom_base_url: str = ""
    custom_api_key: str = ""
    custom_model: str = ""

    # --- Shared LLM settings ---
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048

    @property
    def llm_model(self) -> str:
        """Active model name based on selected provider."""
        return {
            "grok": self.grok_model,
            "openai": self.openai_model,
            "ollama": self.ollama_model,
            "custom": self.custom_model,
        }[self.llm_provider]

    @property
    def llm_base_url(self) -> str:
        """Active base URL based on selected provider."""
        return {
            "grok": self.grok_base_url,
            "openai": self.openai_base_url,
            "ollama": self.ollama_base_url,
            "custom": self.custom_base_url,
        }[self.llm_provider]

    @property
    def llm_api_key(self) -> str:
        """Active API key based on selected provider."""
        return {
            "grok": self.grok_api_key,
            "openai": self.openai_api_key,
            "ollama": self.ollama_api_key,
            "custom": self.custom_api_key,
        }[self.llm_provider]

    # ------------------------------------------------------------------
    # Embeddings
    # NOTE: xAI/Grok does NOT offer an embedding API.
    #   When llm_provider=grok, embedding_backend auto-defaults to
    #   sentence_transformers (local, free, no API key needed).
    # ------------------------------------------------------------------
    embedding_backend: Literal["openai", "sentence_transformers"] = "sentence_transformers"
    embedding_model: str = "text-embedding-3-small"   # used only when backend=openai
    embedding_dimension: int = 384   # 384 for all-MiniLM-L6-v2, 1536 for OpenAI
    sentence_transformer_model: str = "all-MiniLM-L6-v2"

    @property
    def active_embedding_backend(self) -> str:
        """Force sentence_transformers when using Grok (no embedding API)."""
        if self.llm_provider == "grok" and self.embedding_backend == "openai":
            return "sentence_transformers"
        return self.embedding_backend

    # ------------------------------------------------------------------
    # Scraping (inherited from existing module)
    # ------------------------------------------------------------------
    max_concurrent_requests: int = 5
    request_timeout: int = 30
    retry_times: int = 3
    browser_headless: bool = True

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------
    prometheus_enabled: bool = True
    prometheus_path: str = "/metrics"

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------
    pipeline_timeout_seconds: int = 300  # per-stage timeout


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
