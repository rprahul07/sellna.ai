"""Pydantic schemas for Buyer Personas."""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BuyerPersona(BaseModel):
    """Output of Persona Agent."""

    persona_id: UUID = Field(default_factory=uuid4)
    icp_id: UUID
    company_id: UUID
    title: str  # e.g. "VP of Sales"
    seniority: str  # e.g. "C-Level", "Director", "Manager"
    goals: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    buying_triggers: list[str] = Field(default_factory=list)
    preferred_channels: list[str] = Field(default_factory=list)
    messaging_tone: str = "professional"  # professional, friendly, technical
    content_preferences: list[str] = Field(default_factory=list)
    battlecard: dict[str, str] = Field(default_factory=lambda: {
        "winning_strategy": "Be consultative and lead with gap analysis.",
        "competitive_edge": "Focus on our superior RAG-driven context.",
        "key_hook": "Mention their recent industry pivot.",
    })


class PersonaGenerateRequest(BaseModel):
    icp_id: UUID | None = None
    company_id: UUID
    num_personas: int = Field(default=2, ge=1, le=5)
