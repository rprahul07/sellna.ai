"""Gap analysis schemas — market intelligence output."""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MarketGap(BaseModel):
    """A discovered market gap or competitive opportunity."""

    gap_id: UUID = Field(default_factory=uuid4)
    company_id: UUID
    gap_type: str  # "missing_feature" | "underserved_segment" | "messaging_weakness"
    description: str
    opportunity: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    recommended_action: str = ""
