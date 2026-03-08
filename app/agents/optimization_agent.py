"""Optimization Agent — feedback-driven targeting improvement.

Analyzes outreach engagement metrics (open rate, reply rate, conversions)
and provides LLM-generated recommendations for improving targeting and messaging.
"""

from __future__ import annotations

import json
import time
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.outreach import OutreachAsset, OutreachFeedback
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are an expert sales performance analyst.
Analyze engagement metrics and provide specific optimization recommendations.
Return JSON:
{
  "overall_score": 0.0-10.0,
  "performance_summary": "brief assessment",
  "targeting_recommendations": ["rec1", "rec2", "rec3"],
  "messaging_recommendations": ["rec1", "rec2"],
  "a_b_test_ideas": ["test1", "test2"],
  "priority_actions": ["action1", "action2"]
}
Respond with ONLY valid JSON."""


class OptimizationAgent:
    """Analyzes feedback signals and generates optimization recommendations."""

    def __init__(self) -> None:
        self._llm = get_llm_service()

    async def run(
        self,
        assets: list[OutreachAsset],
        feedback_list: list[OutreachFeedback],
    ) -> dict:
        t0 = time.perf_counter()
        logger.info(
            "optimization_agent.start",
            module_name="OptimizationAgent",
            input_summary=f"assets={len(assets)}, feedback={len(feedback_list)}",
        )

        # Merge assets with their feedback
        feedback_map = {str(fb.asset_id): fb for fb in feedback_list}
        merged = []
        for asset in assets:
            fb = feedback_map.get(str(asset.asset_id))
            merged.append({
                "channel": asset.channel,
                "subject": asset.subject[:80],
                "open_rate": fb.open_rate if fb else 0.0,
                "reply_rate": fb.reply_rate if fb else 0.0,
                "conversion_rate": fb.conversion_rate if fb else 0.0,
                "notes": fb.notes if fb else "",
            })

        user_prompt = self._build_prompt(merged)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        raw = await self._llm.chat(messages, json_mode=True, temperature=0.2)
        result = json.loads(raw)

        elapsed = time.perf_counter() - t0
        logger.info(
            "optimization_agent.complete",
            module_name="OptimizationAgent",
            execution_time=round(elapsed, 3),
            output_summary=f"score={result.get('overall_score', 'N/A')}",
        )
        return result

    @staticmethod
    def _build_prompt(merged: list[dict]) -> str:
        rows = "\n".join(
            f"[{m['channel']}] open={m['open_rate']:.0%} reply={m['reply_rate']:.0%} "
            f"conv={m['conversion_rate']:.0%} | {m['subject']}"
            for m in merged
        )
        return (
            f"Outreach performance data:\n{rows}\n\n"
            "Provide detailed optimization recommendations to improve targeting and messaging."
        )
