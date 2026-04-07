"""Competitor Discovery Agent.

Generates search queries, identifies competitors via LLM reasoning,
and produces a validated, ranked list of competitors.
"""

from __future__ import annotations

import json
import time
import uuid
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.company import CompanyAnalysis
from app.schemas.competitor import CompetitorDiscovered
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are a fast analytical engine inside a B2B sales intelligence pipeline.
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

Given company details, identify the top competitors and return structured JSON:
{
  "competitors": [
    {
      "name": "Competitor Name",
      "website": "https://example.com",
      "category": "Direct | Indirect | Alternative",
      "positioning": "One sentence about how they position",
      "relevance_score": 0.0-1.0
    }
  ]
}
Rules:
- Identify 3-5 real, named competitors
- Include only companies that actually exist
- Score: 1.0 = head-to-head competitor, 0.5 = partial overlap, 0.3 = adjacent
- Respond with ONLY valid JSON."""


class CompetitorAgent:
    """Discovers competitors using LLM reasoning from domain analysis."""

    def __init__(self) -> None:
        self._llm = get_llm_service()

    async def run(self, analysis: CompanyAnalysis) -> list[CompetitorDiscovered]:
        t0 = time.perf_counter()
        logger.info(
            "competitor_agent.start",
            module_name="CompetitorAgent",
            company=analysis.company_name,
            input_summary=f"category={analysis.product_category}, segments={len(analysis.target_segments)}",
        )

        user_prompt = self._build_prompt(analysis)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        competitors: list[CompetitorDiscovered] = []
        try:
            raw = await self._llm.chat(messages, json_mode=True, temperature=0.3)
            # Handle potential non-JSON prefix/suffix from some models
            if "{" in raw and "}" in raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                raw = raw[start:end]
            
            data = json.loads(raw)
            for item in data.get("competitors", []):
                try:
                    comp = CompetitorDiscovered(
                        competitor_id=uuid.uuid4(),
                        name=item.get("name", "Unknown Competitor"),
                        website=item.get("website", ""),
                        category=item.get("category", "Direct"),
                        positioning=item.get("positioning", ""),
                        relevance_score=float(item.get("relevance_score", 0.5)),
                        discovery_source="llm_reasoning",
                    )
                    competitors.append(comp)
                except Exception as e:
                    logger.warning("competitor_agent.parse_item_error", error=str(e), item=item)
        except Exception as e:
            logger.error("competitor_agent.error", error=str(e))
            # Fallback — return 0 competitors but don't crash
            return []

        elapsed = time.perf_counter() - t0
        logger.info(
            "competitor_agent.complete",
            module_name="CompetitorAgent",
            execution_time=round(elapsed, 3),
            output_summary=f"discovered={len(competitors)} competitors",
        )
        return competitors

    @staticmethod
    def _build_prompt(analysis: CompanyAnalysis) -> str:
        segments = ", ".join(analysis.target_segments[:5])
        buyer_roles = ", ".join(analysis.buyer_roles[:5])
        return (
            f"Company: {analysis.company_name}\n"
            f"Product Category: {analysis.product_category}\n"
            f"Market Type: {analysis.market_type}\n"
            f"Target Segments: {segments}\n"
            f"Buyer Roles: {buyer_roles}\n"
            f"Positioning: {analysis.competitive_positioning}\n"
            f"Geography: {analysis.raw_input.target_geography}"
        )
