"""Persona Generator Agent.

Takes ICPs and generates detailed buyer personas with:
  - Job title, goals, pain points
  - Objections, buying triggers
  - Preferred communication channels and tone

Uses RAG to incorporate competitor messaging weaknesses into persona design.
"""

from __future__ import annotations

import json
import time
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.company import CompanyAnalysis
from app.schemas.icp import ICPProfile
from app.schemas.persona import BuyerPersona
from app.services.llm_service import get_llm_service
from app.services.rag_service import RAGService

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are an expert sales psychologist and buyer persona specialist.
Create detailed buyer personas for each ICP and return JSON:
{
  "personas": [
    {
      "title": "Exact job title",
      "seniority": "C-Level | VP | Director | Manager | IC",
      "goals": ["goal1", "goal2", "goal3"],
      "pain_points": ["pain1", "pain2", "pain3"],
      "objections": ["objection1", "objection2"],
      "buying_triggers": ["trigger1", "trigger2"],
      "preferred_channels": ["email", "linkedin", "phone"],
      "messaging_tone": "professional | friendly | technical | consultative",
      "content_preferences": ["case_studies", "whitepapers", "demos"]
    }
  ]
}
Respond with ONLY valid JSON."""


class PersonaAgent:
    """Generates buyer personas from ICPs using LLM + optional RAG context."""

    def __init__(self) -> None:
        self._llm = get_llm_service()
        self._rag = RAGService()

    async def run(
        self,
        company_analysis: CompanyAnalysis,
        icps: list[ICPProfile],
        num_personas_per_icp: int = 2,
        rag_collection: str | None = None,
    ) -> list[BuyerPersona]:
        t0 = time.perf_counter()
        logger.info(
            "persona_agent.start",
            module_name="PersonaAgent",
            company=company_analysis.company_name,
            input_summary=f"icps={len(icps)}, personas_per_icp={num_personas_per_icp}",
        )

        all_personas: list[BuyerPersona] = []

        for icp in icps:
            # Optionally enrich prompt with RAG context
            rag_context = ""
            if rag_collection:
                query = f"buyer personas for {icp.industry} {icp.buyer_authority}"
                rag_context = "\n\nRelevant context from competitor intelligence:\n" + "\n".join(
                    await self._rag.retrieve(rag_collection, query, top_k=3)
                )

            prompt = self._build_prompt(company_analysis, icp, num_personas_per_icp, rag_context)
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            raw = await self._llm.chat(messages, json_mode=True, temperature=0.4)
            data = json.loads(raw)

            for item in data.get("personas", []):
                try:
                    persona = BuyerPersona(
                        icp_id=icp.icp_id,
                        company_id=company_analysis.company_id,
                        title=item.get("title", ""),
                        seniority=item.get("seniority", "Director"),
                        goals=item.get("goals", []),
                        pain_points=item.get("pain_points", []),
                        objections=item.get("objections", []),
                        buying_triggers=item.get("buying_triggers", []),
                        preferred_channels=item.get("preferred_channels", ["email"]),
                        messaging_tone=item.get("messaging_tone", "professional"),
                        content_preferences=item.get("content_preferences", []),
                    )
                    all_personas.append(persona)
                except Exception as e:
                    logger.warning("persona_agent.parse_error", error=str(e))

        elapsed = time.perf_counter() - t0
        logger.info(
            "persona_agent.complete",
            module_name="PersonaAgent",
            execution_time=round(elapsed, 3),
            output_summary=f"personas={len(all_personas)}",
        )
        return all_personas

    @staticmethod
    def _build_prompt(
        analysis: CompanyAnalysis,
        icp: ICPProfile,
        n: int,
        rag_context: str,
    ) -> str:
        return (
            f"Company: {analysis.company_name}\n"
            f"Product: {analysis.raw_input.product_description[:300]}\n"
            f"Core Problem: {analysis.raw_input.core_problem_solved}\n\n"
            f"ICP:\n"
            f"  Industry: {icp.industry}\n"
            f"  Size: {icp.company_size}\n"
            f"  Revenue: {icp.revenue_range}\n"
            f"  Buyer Authority: {icp.buyer_authority}\n"
            f"  Pain Points: {', '.join(icp.pain_points[:4])}\n"
            f"  Buying Signals: {', '.join(icp.buying_signals[:3])}\n"
            f"{rag_context}\n\n"
            f"Generate {n} detailed personas for this ICP."
        )
