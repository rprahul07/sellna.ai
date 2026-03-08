"""Embedding Service — async text-to-vector conversion.

Supports:
  - SentenceTransformers (local, FREE, default when using Grok)
      → model: all-MiniLM-L6-v2  (384 dims, ~90MB, runs on CPU)
  - OpenAI embeddings (only available when LLM_PROVIDER=openai)
      → model: text-embedding-3-small (1536 dims)

xAI/Grok does NOT offer an embedding API — so when LLM_PROVIDER=grok
the service automatically uses SentenceTransformers at no cost.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Sequence

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()


class EmbeddingService:
    """Get dense vector embeddings for one or more text strings."""

    def __init__(self) -> None:
        # active_embedding_backend auto-forces sentence_transformers when provider=grok
        self._backend = _settings.active_embedding_backend
        logger.info(
            "embedding_service.init",
            backend=self._backend,
            llm_provider=_settings.llm_provider,
        )
        if self._backend == "sentence_transformers":
            self._init_st()
        else:
            self._init_openai()

    def _init_openai(self) -> None:
        from openai import AsyncOpenAI

        # Use OpenAI key specifically for embeddings (separate from LLM provider)
        self._client = AsyncOpenAI(
            api_key=_settings.openai_api_key or "sk-placeholder",
            base_url=_settings.openai_base_url,
        )
        self._model = _settings.embedding_model

    def _init_st(self) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._st_model = SentenceTransformer(_settings.sentence_transformer_model)

    # ------------------------------------------------------------------

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._backend == "sentence_transformers":
            return await self._embed_st(texts)
        return await self._embed_openai(texts)

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self._client.embeddings.create(
                model=self._model, input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as exc:
            logger.error("embedding.openai.error", error=str(exc))
            raise

    async def _embed_st(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            None, lambda: self._st_model.encode(texts, normalize_embeddings=True).tolist()
        )
        return embeddings


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
