"""Pydantic schemas for Company Intelligence (Module 1)."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


class PricingModel(str, Enum):
    freemium = "freemium"
    subscription = "subscription"
    usage_based = "usage_based"
    enterprise = "enterprise"
    one_time = "one_time"
    other = "other"


class CustomerType(str, Enum):
    b2b = "B2B"
    b2c = "B2C"
    b2b2c = "B2B2C"
    government = "Government"
    marketplace = "Marketplace"


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class CompanyInput(BaseModel):
    """Complete company context required before any pipeline stage runs."""

    company_name: str = Field(..., min_length=1, max_length=200)
    product_description: str = Field(..., min_length=10)
    industry: str = Field(..., description="e.g. 'SaaS', 'FinTech', 'Healthcare'")
    target_geography: str = Field(..., description="e.g. 'North America', 'Global'")
    pricing_model: PricingModel
    customer_type: CustomerType
    core_problem_solved: str = Field(..., min_length=10)
    product_features: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    website: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# Output / Analysis
# ---------------------------------------------------------------------------


class MarketType(str, Enum):
    horizontal = "horizontal"
    vertical = "vertical"
    niche = "niche"
    enterprise = "enterprise"


class CompanyAnalysis(BaseModel):
    """Domain Intelligence Agent output."""

    company_id: UUID = Field(default_factory=uuid4)
    company_name: str
    market_type: MarketType
    target_segments: list[str]
    pain_points: list[str]
    buyer_roles: list[str]
    product_category: str
    competitive_positioning: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    raw_input: CompanyInput
