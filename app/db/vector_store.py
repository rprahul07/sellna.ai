"""Vector store abstraction — supports Qdrant and FAISS.

Usage:
    from app.db.vector_store import get_vector_store
    vs = get_vector_store()
    await vs.upsert("collection", id, embedding, payload)
    results = await vs.search("collection", query_embedding, top_k=5)
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


class VectorSearchResult:
    def __init__(self, id: str, score: float, payload: dict[str, Any]):
        self.id = id
        self.score = score
        self.payload = payload


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class VectorStore(ABC):
    @abstractmethod
    async def upsert(
        self,
        collection: str,
        doc_id: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None: ...

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> list[VectorSearchResult]: ...

    @abstractmethod
    async def delete(self, collection: str, doc_id: str) -> None: ...


# ---------------------------------------------------------------------------
# Qdrant implementation
# ---------------------------------------------------------------------------


class QdrantVectorStore(VectorStore):
    def __init__(self) -> None:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._client = AsyncQdrantClient(
            url=_settings.qdrant_url,
            api_key=_settings.qdrant_api_key,
        )
        self._Distance = Distance
        self._VectorParams = VectorParams
        self._dim = _settings.embedding_dimension

    async def _ensure_collection(self, collection: str) -> None:
        from qdrant_client.models import Distance, VectorParams
        collections = await self._client.get_collections()
        names = [c.name for c in collections.collections]
        if collection not in names:
            await self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )

    async def upsert(
        self,
        collection: str,
        doc_id: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        from qdrant_client.models import PointStruct
        await self._ensure_collection(collection)
        point = PointStruct(id=doc_id, vector=embedding, payload=payload)
        await self._client.upsert(collection_name=collection, points=[point])

    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> list[VectorSearchResult]:
        await self._ensure_collection(collection)
        hits = await self._client.query_points(
            collection_name=collection,
            query=query_embedding,
            limit=top_k,
            score_threshold=score_threshold,
        )
        return [
            VectorSearchResult(id=str(hit.id), score=hit.score, payload=hit.payload or {})
            for hit in hits.points
        ]

    async def delete(self, collection: str, doc_id: str) -> None:
        from qdrant_client.models import PointIdsList
        await self._client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=[doc_id]),
        )


# ---------------------------------------------------------------------------
# FAISS implementation (sync, run in executor)
# ---------------------------------------------------------------------------


class FAISSVectorStore(VectorStore):
    """Lightweight local FAISS store. Not recommended for production scale."""

    def __init__(self) -> None:
        import faiss  # type: ignore
        import numpy as np

        self._faiss = faiss
        self._np = np
        self._dim = _settings.embedding_dimension
        self._index_path = Path(_settings.faiss_index_path)
        self._index_path.mkdir(parents=True, exist_ok=True)
        self._indices: dict[str, Any] = {}
        self._payloads: dict[str, dict[str, Any]] = {}  # collection -> {id: payload}
        self._ids: dict[str, list[str]] = {}  # collection -> [id, ...]

    def _get_index(self, collection: str):
        if collection not in self._indices:
            idx = self._faiss.IndexFlatIP(self._dim)  # inner product ≈ cosine if normalized
            self._indices[collection] = idx
            self._payloads[collection] = {}
            self._ids[collection] = []
        return self._indices[collection]

    async def upsert(
        self,
        collection: str,
        doc_id: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._upsert_sync, collection, doc_id, embedding, payload)

    def _upsert_sync(self, collection: str, doc_id: str, embedding: list[float], payload: dict) -> None:
        import numpy as np
        idx = self._get_index(collection)
        vec = np.array([embedding], dtype="float32")
        self._faiss.normalize_L2(vec)
        idx.add(vec)
        self._ids[collection].append(doc_id)
        self._payloads[collection][doc_id] = payload

    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> list[VectorSearchResult]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._search_sync, collection, query_embedding, top_k, score_threshold
        )

    def _search_sync(
        self, collection: str, query_embedding: list[float], top_k: int, threshold: float
    ) -> list[VectorSearchResult]:
        import numpy as np
        idx = self._get_index(collection)
        if idx.ntotal == 0:
            return []
        vec = np.array([query_embedding], dtype="float32")
        self._faiss.normalize_L2(vec)
        scores, indices = idx.search(vec, min(top_k, idx.ntotal))
        results = []
        ids = self._ids[collection]
        payloads = self._payloads[collection]
        for score, i in zip(scores[0], indices[0]):
            if i < 0 or score < threshold:
                continue
            doc_id = ids[i]
            results.append(VectorSearchResult(id=doc_id, score=float(score), payload=payloads.get(doc_id, {})))
        return results

    async def delete(self, collection: str, doc_id: str) -> None:
        # FAISS flat index doesn't support direct deletion; mark as removed
        if collection in self._payloads:
            self._payloads[collection].pop(doc_id, None)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    backend = _settings.vector_store
    logger.info("vector_store.init", backend=backend)
    if backend == "qdrant":
        return QdrantVectorStore()
    return FAISSVectorStore()
