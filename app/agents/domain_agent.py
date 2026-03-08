"""Domain Intelligence Agent — Module 1.

Accepts company input and produces a comprehensive market analysis using
LLM reasoning + taxonomy classification. This output feeds every downstream
agent in the pipeline.
"""

from __future__ import annotations

import json
import time
from uuid import UUID

from app.config import get_settings
from app.core.logging import get_logger
from app.schemas.company import (
    CompanyAnalysis,
    CompanyInput,
    MarketType,
)
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)
_settings = get_settings()

_SYSTEM_PROMPT = """You are an expert B2B market analyst and sales strategist.
Analyze the provided company details and return a structured JSON object with:
{
  "market_type": one of ["horizontal", "vertical", "niche", "enterprise"],
  "target_segments": [list of 3-5 specific market segments],
  "pain_points": [list of 4-6 pain points the product addresses],
  "buyer_roles": [list of 3-5 specific job titles who buy this],
  "product_category": "single category string",
  "competitive_positioning": "1-2 sentence positioning statement",
  "strengths": [list of 3-5 product strengths],
  "weaknesses": [list of 2-3 potential weaknesses or gaps]
}
Respond with ONLY valid JSON. No markdown, no explanation."""


class DomainAgent:
    """Stateless agent — takes CompanyInput, returns CompanyAnalysis."""

    def __init__(self) -> None:
        self._llm = get_llm_service()

    async def run(self, company_input: CompanyInput) -> CompanyAnalysis:
        t0 = time.perf_counter()
        logger.info(
            "domain_agent.start",
            module_name="DomainAgent",
            company=company_input.company_name,
            input_summary=f"industry={company_input.industry}, type={company_input.customer_type}",
        )

        user_prompt = self._build_prompt(company_input)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        raw = await self._llm.chat(messages, json_mode=True, temperature=0.2)
        data = json.loads(raw)

        analysis = CompanyAnalysis(
            company_name=company_input.company_name,
            market_type=MarketType(data.get("market_type", "horizontal")),
            target_segments=data.get("target_segments", []),
            pain_points=data.get("pain_points", []),
            buyer_roles=data.get("buyer_roles", []),
            product_category=data.get("product_category", ""),
            competitive_positioning=data.get("competitive_positioning", ""),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            raw_input=company_input,
        )

        elapsed = time.perf_counter() - t0
        logger.info(
            "domain_agent.complete",
            module_name="DomainAgent",
            execution_time=round(elapsed, 3),
            output_summary=(
                f"market_type={analysis.market_type}, "
                f"segments={len(analysis.target_segments)}, "
                f"buyer_roles={len(analysis.buyer_roles)}"
            ),
        )
        return analysis

    @staticmethod
    def _build_prompt(inp: CompanyInput) -> str:
        features = ", ".join(inp.product_features[:10]) if inp.product_features else "Not provided"
        tech = ", ".join(inp.tech_stack[:10]) if inp.tech_stack else "Not provided"
        return (
            f"Company: {inp.company_name}\n"
            f"Product: {inp.product_description}\n"
            f"Industry: {inp.industry}\n"
            f"Target Geography: {inp.target_geography}\n"
            f"Pricing Model: {inp.pricing_model}\n"
            f"Customer Type: {inp.customer_type}\n"
            f"Core Problem: {inp.core_problem_solved}\n"
            f"Features: {features}\n"
            f"Tech Stack: {tech}\n"
            f"Website: {inp.website or 'Not provided'}"
        )
