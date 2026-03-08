"""ICP Generator Agent.

Generates Ideal Customer Profiles from:
  - Company analysis (domain intel)
  - Market gaps (what segments are underserved)
Uses LLM to produce structured, actionable ICP profiles.
"""

from __future__ import annotations

import json
import time
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.company import CompanyAnalysis
from app.schemas.gap_analysis import MarketGap
from app.schemas.icp import ICPProfile
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are an expert sales strategist specializing in ICP definition.
Generate Ideal Customer Profiles and return a JSON object:
{
  "icps": [
    {
      "industry": "specific industry vertical",
      "company_size": "e.g. 50-200 employees",
      "revenue_range": "e.g. $5M-$20M ARR",
      "tech_stack": ["tool1", "tool2"],
      "buyer_authority": "specific title",
      "geography": "region",
      "pain_points": ["pain1", "pain2"],
      "buying_signals": ["signal1", "signal2"],
      "exclusion_criteria": ["exclude1"],
      "fit_score_rationale": "why this is a perfect fit"
    }
  ]
}
Respond with ONLY valid JSON."""


class ICPAgent:
    """Generates Ideal Customer Profiles using domain analysis + gap intelligence."""

    def __init__(self) -> None:
        self._llm = get_llm_service()

    async def run(
        self,
        analysis: CompanyAnalysis,
        gaps: list[MarketGap],
        num_profiles: int = 3,
    ) -> list[ICPProfile]:
        t0 = time.perf_counter()
        logger.info(
            "icp_agent.start",
            module_name="ICPAgent",
            company=analysis.company_name,
            input_summary=f"gaps={len(gaps)}, requested={num_profiles}",
        )

        user_prompt = self._build_prompt(analysis, gaps, num_profiles)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        raw = await self._llm.chat(messages, json_mode=True, temperature=0.3)
        data = json.loads(raw)

        profiles: list[ICPProfile] = []
        for item in data.get("icps", []):
            try:
                icp = ICPProfile(
                    company_id=analysis.company_id,
                    industry=item.get("industry", ""),
                    company_size=item.get("company_size", ""),
                    revenue_range=item.get("revenue_range", ""),
                    tech_stack=item.get("tech_stack", []),
                    buyer_authority=item.get("buyer_authority", ""),
                    geography=item.get("geography", analysis.raw_input.target_geography),
                    pain_points=item.get("pain_points", []),
                    buying_signals=item.get("buying_signals", []),
                    exclusion_criteria=item.get("exclusion_criteria", []),
                    fit_score_rationale=item.get("fit_score_rationale", ""),
                )
                profiles.append(icp)
            except Exception as e:
                logger.warning("icp_agent.parse_error", error=str(e))

        elapsed = time.perf_counter() - t0
        logger.info(
            "icp_agent.complete",
            module_name="ICPAgent",
            execution_time=round(elapsed, 3),
            output_summary=f"icps={len(profiles)}",
        )
        return profiles[:num_profiles]

    @staticmethod
    def _build_prompt(analysis: CompanyAnalysis, gaps: list[MarketGap], n: int) -> str:
        gap_summaries = "\n".join(
            f"- [{g.gap_type}] {g.description} → {g.opportunity}"
            for g in gaps[:6]
        )
        return (
            f"Company: {analysis.company_name}\n"
            f"Product Category: {analysis.product_category}\n"
            f"Target Geography: {analysis.raw_input.target_geography}\n"
            f"Customer Type: {analysis.raw_input.customer_type}\n"
            f"Pricing Model: {analysis.raw_input.pricing_model}\n"
            f"Buyer Roles: {', '.join(analysis.buyer_roles[:5])}\n"
            f"Market Segments: {', '.join(analysis.target_segments[:5])}\n"
            f"Market Gaps:\n{gap_summaries}\n\n"
            f"Generate {n} highly specific ICPs."
        )
