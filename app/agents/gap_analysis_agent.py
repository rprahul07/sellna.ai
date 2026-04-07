"""Gap Analysis Agent — core competitive intelligence.

Uses embeddings + vector search + LLM reasoning via RAG to find:
  - Missing features
  - Underserved market segments
  - Messaging weaknesses

Context sources:
  - Competitor clean data (indexed once per pipeline run)
  - Domain analysis (company pain points, buyer roles)
"""

from __future__ import annotations

import json
import time
import uuid
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.company import CompanyAnalysis
from app.schemas.competitor import CompetitorCleanData
from app.schemas.gap_analysis import MarketGap
from app.services.llm_service import get_llm_service
from app.services.rag_service import RAGService

logger = get_logger(__name__)

_SYSTEM_GAP = """You are a fast analytical engine inside a B2B sales intelligence pipeline.
Your job is to extract only the most important insights from the provided context.
Strict rules:
Use ONLY the information present in the context.
Do NOT explain reasoning.
Do NOT restate the context.
Extract the minimal information needed to answer the question.
Keep the response extremely concise.
Maximum output length: 120 words.
Focus only on actionable insights.
Ignore irrelevant competitor information.
If the answer is not clearly supported by the context, return:
{"result": "insufficient_context"}
Return the output as valid JSON only.
Do not perform step-by-step reasoning.
Extract answers directly.

Return a JSON object:
{
  "gaps": [
    {
      "gap_type": "missing_feature | underserved_segment | messaging_weakness",
      "description": "What the gap is",
      "opportunity": "How the company can exploit this gap",
      "confidence_score": 0.0-1.0,
      "supporting_evidence": ["evidence1", "evidence2"],
      "recommended_action": "Specific action to take"
    }
  ]
}
Identify 2-4 gaps. Respond with ONLY valid JSON."""


class GapAnalysisAgent:
    """RAG-powered gap analysis over competitor landscape."""

    def __init__(self) -> None:
        self._rag = RAGService()
        self._llm = get_llm_service()

    async def run(
        self,
        analysis: CompanyAnalysis,
        clean_data_list: list[CompetitorCleanData],
    ) -> list[MarketGap]:
        t0 = time.perf_counter()
        company_id = analysis.company_id
        collection = f"gap_{company_id}"

        logger.info(
            "gap_analysis_agent.start",
            module_name="GapAnalysisAgent",
            company=analysis.company_name,
            input_summary=f"competitor_docs={len(clean_data_list)}",
        )

        # Index competitor documents into vector store (Chunked for latency)
        documents = []
        for cd in clean_data_list:
            text = cd.normalized_text.strip()
            if not text:
                continue
            chunk_size = 2500
            for i in range(0, len(text), chunk_size):
                documents.append(text[i : i + chunk_size + 200])
        if not documents:
            logger.warning("gap_analysis_agent.no_competitors", message="No competitor data to index. Using domain knowledge as fallback.")
        else:
            await self._rag.index_documents(collection, documents)

        # Build company context
        company_context = self._build_context(analysis)

        # RAG query for each gap type
        gap_query = (
            f"Identify 2-4 specific market gaps (missing features, underserved segments, or messaging weaknesses) "
            f"where this company could successfully compete.\n"
            f"Company profile: {company_context}"
        )

        try:
            raw = await self._rag.query(
                collection=collection,
                question=gap_query,
                system_prompt=_SYSTEM_GAP,
                top_k=3,
                json_mode=True,
            )
            data = json.loads(raw)
        except Exception as e:
            logger.warning("gap_analysis_agent.rag_failed", error=str(e))
            data = {"gaps": []}

        # Fallback: if no gaps found via RAG, generate them based on company strengths
        if not data.get("gaps"):
            logger.info("gap_analysis_agent.fallback_mode")
            fallback_prompt = (
                f"Based on this company profile, suggest 3 high-level market gaps they are well-positioned to fill.\n"
                f"Profile: {company_context}\n\n"
                "Return JSON: {\"gaps\": [{\"gap_type\": \"underserved_segment\", \"description\": \"...\", \"opportunity\": \"...\", \"confidence_score\": 0.7, \"supporting_evidence\": [], \"recommended_action\": \"...\"}]}"
            )
            raw = await self._llm.chat([{"role": "system", "content": _SYSTEM_GAP}, {"role": "user", "content": fallback_prompt}], json_mode=True)
            data = json.loads(raw)

        gaps: list[MarketGap] = []

        for item in data.get("gaps", []):
            try:
                gap = MarketGap(
                    company_id=company_id,
                    gap_type=item.get("gap_type", "missing_feature"),
                    description=item.get("description", ""),
                    opportunity=item.get("opportunity", ""),
                    confidence_score=float(item.get("confidence_score", 0.5)),
                    supporting_evidence=item.get("supporting_evidence", []),
                    recommended_action=item.get("recommended_action", ""),
                )
                gaps.append(gap)
            except Exception as e:
                logger.warning("gap_analysis_agent.parse_error", error=str(e))

        elapsed = time.perf_counter() - t0
        logger.info(
            "gap_analysis_agent.complete",
            module_name="GapAnalysisAgent",
            execution_time=round(elapsed, 3),
            output_summary=f"gaps={len(gaps)}",
        )
        return gaps

    @staticmethod
    def _build_context(analysis: CompanyAnalysis) -> str:
        return (
            f"Company: {analysis.company_name}. "
            f"Category: {analysis.product_category}. "
            f"Market: {analysis.market_type}. "
            f"Pain points: {', '.join(analysis.pain_points[:4])}. "
            f"Features strengths: {', '.join(analysis.strengths[:4])}. "
            f"Weaknesses: {', '.join(analysis.weaknesses[:3])}."
        )
