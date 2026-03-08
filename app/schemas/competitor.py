"""Pydantic schemas for competitor discovery and web intelligence."""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CompetitorBase(BaseModel):
    name: str
    website: str
    category: str
    positioning: str


class CompetitorDiscovered(CompetitorBase):
    """Output of Competitor Discovery Agent."""

    competitor_id: UUID = Field(default_factory=uuid4)
    relevance_score: float = Field(ge=0.0, le=1.0, default=0.5)
    discovery_source: str = "llm_search"


class CompetitorWebData(BaseModel):
    """Output of Web Intelligence Agent for a single competitor."""

    competitor_id: UUID
    website: str
    features: list[str] = Field(default_factory=list)
    pricing_tiers: list[str] = Field(default_factory=list)
    marketing_copy: str = ""
    value_proposition: str = ""
    target_audience: str = ""
    raw_headings: dict[str, list[str]] = Field(default_factory=dict)
    raw_paragraphs: list[str] = Field(default_factory=list)
    scrape_success: bool = False
    error: Optional[str] = None


class CompetitorCleanData(BaseModel):
    """Output of Cleaning Agent for a single competitor."""

    competitor_id: UUID
    clean_features: list[str] = Field(default_factory=list)
    clean_pricing: str = ""
    clean_positioning: str = ""
    clean_value_proposition: str = ""
    normalized_text: str = ""
