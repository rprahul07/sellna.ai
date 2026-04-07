"""Outreach Agent.

Generates personalized outreach content for each persona:
  - Cold email (subject + body + CTA)
  - LinkedIn message
  - Call opener script

RAG is used to ground messaging in competitor gaps and buyer context.
"""

from __future__ import annotations

import asyncio
import json
import time
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.company import CompanyAnalysis
from app.schemas.outreach import OutreachAsset
from app.schemas.persona import BuyerPersona
from app.services.llm_service import get_llm_service
from app.services.rag_service import RAGService

logger = get_logger(__name__)

_CHANNEL_PROMPTS = {
    "cold_email": """Generate a personalized cold email for this persona.
Return JSON:
{
  "subject": "compelling subject line (max 60 chars)",
  "body": "full email body (150-250 words, plain text)",
  "call_to_action": "specific CTA",
  "personalization_tokens": {"{{pain_point}}": "value", "{{trigger}}": "value"}
}""",
    "linkedin": """Generate a personalized LinkedIn connection request + follow-up message.
Return JSON:
{
  "subject": "LinkedIn connection request note (max 300 chars)",
  "body": "LinkedIn follow-up message after connecting (100-150 words)",
  "call_to_action": "specific low-friction CTA",
  "personalization_tokens": {}
}""",
    "call_opener": """Generate a cold call opener script (30-second pitch).
Return JSON:
{
  "subject": "Pattern interrupt opener line",
  "body": "Full 30-second call opener script (conversational, not salesy)",
  "call_to_action": "Specific ask (meeting, demo, etc.)",
  "personalization_tokens": {"{{company}}": "their company name"}
}""",
}


class OutreachAgent:
    """Generates personalized multi-channel outreach content."""

    def __init__(self) -> None:
        self._llm = get_llm_service()
        self._rag = RAGService()

    async def run(
        self,
        persona: BuyerPersona,
        analysis: CompanyAnalysis,
        channels: list[str] | None = None,
        rag_collection: str | None = None,
    ) -> list[OutreachAsset]:
        if channels is None:
            channels = ["cold_email", "linkedin", "call_opener"]

        t0 = time.perf_counter()
        logger.info(
            "outreach_agent.start",
            module_name="OutreachAgent",
            persona=persona.title,
            channels=channels,
        )

        # Retrieve relevant context via RAG
        rag_context = ""
        if rag_collection:
            query = f"messaging for {persona.title} dealing with {', '.join(persona.pain_points[:2])}"
            chunks = await self._rag.retrieve(rag_collection, query, top_k=3)
            rag_context = "\n\nCompetitor intelligence context:\n" + "\n".join(chunks)

        # Run sequentially to prevent overwhelming free LLM APIs (503 Service Unavailable)
        assets: list[OutreachAsset] = []
        for channel in channels:
            asset = await self._generate_for_channel(persona, analysis, channel, rag_context)
            if asset:
                assets.append(asset)

        elapsed = time.perf_counter() - t0
        logger.info(
            "outreach_agent.complete",
            module_name="OutreachAgent",
            execution_time=round(elapsed, 3),
            output_summary=f"assets={len(assets)} for {persona.title}",
        )
        return assets

    async def _generate_for_channel(
        self,
        persona: BuyerPersona,
        analysis: CompanyAnalysis,
        channel: str,
        rag_context: str,
    ) -> OutreachAsset | None:
        channel_instruction = _CHANNEL_PROMPTS.get(channel, _CHANNEL_PROMPTS["cold_email"])
        prompt = self._build_prompt(persona, analysis, channel_instruction, rag_context)

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
Extract answers directly."""

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await self._llm.chat(messages, json_mode=True, temperature=0.6)
            data = json.loads(raw)
            return OutreachAsset(
                persona_id=persona.persona_id,
                company_id=persona.company_id,
                channel=channel,
                subject=data.get("subject", ""),
                body=data.get("body", ""),
                call_to_action=data.get("call_to_action", ""),
                personalization_tokens={
                    str(k): (v if isinstance(v, (str, int, float, bool)) else json.dumps(v))
                    for k, v in data.get("personalization_tokens", {}).items()
                } if isinstance(data.get("personalization_tokens"), dict) else {},
            )
        except Exception as e:
            logger.warning("outreach_agent.channel_error", channel=channel, error=str(e))
            return None

    @staticmethod
    def _build_prompt(
        persona: BuyerPersona,
        analysis: CompanyAnalysis,
        channel_instruction: str,
        rag_context: str,
    ) -> str:
        return (
            f"Company selling: {analysis.company_name}\n"
            f"Product: {analysis.raw_input.product_description[:200]}\n"
            f"Core Problem Solved: {analysis.raw_input.core_problem_solved}\n\n"
            f"Target Persona:\n"
            f"  Title: {persona.title}\n"
            f"  Seniority: {persona.seniority}\n"
            f"  Goals: {', '.join(persona.goals[:3])}\n"
            f"  Pain Points: {', '.join(persona.pain_points[:3])}\n"
            f"  Objections: {', '.join(persona.objections[:2])}\n"
            f"  Buying Triggers: {', '.join(persona.buying_triggers[:2])}\n"
            f"  Preferred Tone: {persona.messaging_tone}\n"
            f"{rag_context}\n\n"
            f"{channel_instruction}"
        )
