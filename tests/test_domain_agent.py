"""Tests for the Domain Intelligence Agent."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.domain_agent import DomainAgent
from app.schemas.company import CompanyInput, CustomerType, PricingModel


@pytest.fixture
def sample_input() -> CompanyInput:
    return CompanyInput(
        company_name="Acme SaaS",
        product_description="AI-powered CRM for sales teams",
        industry="SaaS / CRM",
        target_geography="North America",
        pricing_model=PricingModel.subscription,
        customer_type=CustomerType.b2b,
        core_problem_solved="Sales teams waste 3+ hours daily on manual data entry",
        product_features=["Auto-logging", "Pipeline AI", "Email sequencing"],
        tech_stack=["Python", "React", "PostgreSQL"],
        website="https://acme-saas.example.com",
    )


@pytest.mark.asyncio
async def test_domain_agent_returns_analysis(sample_input):
    """Domain agent should return a CompanyAnalysis when LLM responds correctly."""
    mock_response = json.dumps({
        "market_type": "horizontal",
        "target_segments": ["Mid-market B2B", "Enterprise SaaS teams"],
        "pain_points": ["Manual data entry", "Poor pipeline visibility"],
        "buyer_roles": ["VP of Sales", "Head of Revenue Ops"],
        "product_category": "CRM / Sales Intelligence",
        "competitive_positioning": "AI-first CRM eliminating manual work",
        "strengths": ["AI automation", "Fast onboarding"],
        "weaknesses": ["Limited mobile app"],
    })

    with patch(
        "app.services.llm_service.LLMService.chat",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        agent = DomainAgent()
        result = await agent.run(sample_input)

    assert result.company_name == "Acme SaaS"
    assert result.market_type.value == "horizontal"
    assert len(result.target_segments) == 2
    assert len(result.buyer_roles) == 2
    assert result.product_category == "CRM / Sales Intelligence"


@pytest.mark.asyncio
async def test_domain_agent_handles_partial_llm_response(sample_input):
    """Agent should handle missing optional fields gracefully."""
    mock_response = json.dumps({
        "market_type": "vertical",
        "target_segments": [],
        "pain_points": [],
        "buyer_roles": [],
        "product_category": "CRM",
        "competitive_positioning": "",
        "strengths": [],
        "weaknesses": [],
    })

    with patch(
        "app.services.llm_service.LLMService.chat",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        agent = DomainAgent()
        result = await agent.run(sample_input)

    assert result is not None
    assert result.market_type.value == "vertical"
