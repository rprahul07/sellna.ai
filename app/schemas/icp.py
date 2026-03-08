"""Pydantic schemas for Ideal Customer Profiles."""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ICPProfile(BaseModel):
    """Output of ICP Agent."""

    icp_id: UUID = Field(default_factory=uuid4)
    company_id: UUID
    industry: str
    company_size: str  # e.g. "50-200 employees"
    revenue_range: str  # e.g. "$5M-$20M ARR"
    tech_stack: list[str] = Field(default_factory=list)
    buyer_authority: str  # e.g. "VP of Sales, Head of Growth"
    geography: str
    pain_points: list[str] = Field(default_factory=list)
    buying_signals: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    fit_score_rationale: str = ""


class ICPGenerateRequest(BaseModel):
    company_id: UUID
    num_profiles: int = Field(default=3, ge=1, le=10)
