"""RAG Service — Retrieval-Augmented Generation.

Custom minimal RAG pipeline (LangChain-inspired, no LangChain dependency):

1. Index:   embed documents → store in VectorDB
2. Retrieve: embed query → top-k similarity search
3. Generate: inject retrieved chunks as context → LLM completion

Usage:
    rag = RAGService()
    await rag.index_documents("gap_analysis", docs)
    answer = await rag.query("gap_analysis", "What features are missing?")
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger
from app.db.vector_store import get_vector_store
from app.services.embedding_service import get_embedding_service
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)
_settings = get_settings()


class RAGService:
    """Retrieval-Augmented Generation over a named collection."""

    def __init__(self) -> None:
        self._vs = get_vector_store()
        self._embed = get_embedding_service()
        self._llm = get_llm_service()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_documents(
        self,
        collection: str,
        documents: list[str],
        payloads: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """Embed and store documents. Returns list of assigned doc IDs."""
        if not documents:
            return []

        embeddings = await self._embed.embed_batch(documents)
        ids: list[str] = []

        for i, (doc, emb) in enumerate(zip(documents, embeddings)):
            doc_id = str(uuid.uuid4())
            payload: dict[str, Any] = {"text": doc}
            if payloads and i < len(payloads):
                payload.update(payloads[i])
            await self._vs.upsert(collection, doc_id, emb, payload)
            ids.append(doc_id)

        logger.info("rag.indexed", collection=collection, count=len(ids))
        return ids

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.3,
    ) -> list[str]:
        """Return top-k relevant text chunks for a query."""
        query_emb = await self._embed.embed_one(query)
        hits = await self._vs.search(collection, query_emb, top_k=top_k, score_threshold=score_threshold)
        return [hit.payload.get("text", "") for hit in hits]

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def query(
        self,
        collection: str,
        question: str,
        system_prompt: str = "",
        top_k: int = 5,
        json_mode: bool = False,
    ) -> str:
        """Full RAG cycle: retrieve → augment → generate."""
        chunks = await self.retrieve(collection, question, top_k=top_k)

        if not system_prompt:
            system_prompt = (
                "You are a strategic sales intelligence expert. "
                "Answer the question using ONLY the provided context. "
                "Be specific and actionable."
            )

        context = "\n\n---\n\n".join(chunks) if chunks else "No context available."

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Context:\n{context}\n\n"
                    f"Question: {question}"
                ),
            },
        ]

        answer = await self._llm.chat(messages, json_mode=json_mode)
        logger.info("rag.query.complete", collection=collection, chunks_used=len(chunks))
        return answer

    # ------------------------------------------------------------------
    # Convenience: index + query in one call
    # ------------------------------------------------------------------

    async def index_and_query(
        self,
        collection: str,
        documents: list[str],
        question: str,
        system_prompt: str = "",
        top_k: int = 5,
        json_mode: bool = False,
    ) -> str:
        await self.index_documents(collection, documents)
        return await self.query(collection, question, system_prompt=system_prompt, top_k=top_k, json_mode=json_mode)
