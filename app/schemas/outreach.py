"""Pydantic schemas for Outreach content generation."""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OutreachAsset(BaseModel):
    """A single piece of generated outreach content."""

    asset_id: UUID = Field(default_factory=uuid4)
    persona_id: UUID
    company_id: UUID
    channel: str  # "cold_email" | "linkedin" | "call_opener"
    subject: str = ""  # for email
    body: str
    call_to_action: str = ""
    personalization_tokens: dict[str, Any] = Field(default_factory=dict)


class OutreachGenerateRequest(BaseModel):
    persona_id: UUID
    company_id: UUID
    channels: list[str] = Field(
        default=["cold_email", "linkedin", "call_opener"],
        description="List of channels to generate content for",
    )


class OutreachFeedback(BaseModel):
    """Engagement signal for a sent outreach asset."""

    asset_id: UUID
    open_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    reply_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    conversion_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    notes: str = ""
