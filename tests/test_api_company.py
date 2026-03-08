"""API integration tests for Company Intelligence endpoints."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch

SAMPLE_COMPANY = {
    "company_name": "Acme Sales AI",
    "product_description": "AI-powered outreach platform for B2B sales teams",
    "industry": "SaaS",
    "target_geography": "North America",
    "pricing_model": "subscription",
    "customer_type": "B2B",
    "core_problem_solved": "Sales teams struggle with personalized outreach at scale",
    "product_features": ["AI email generation", "CRM sync", "Analytics dashboard"],
    "tech_stack": ["Python", "React"],
    "website": "https://acme.example.com",
}

MOCK_ANALYSIS = {
    "market_type": "horizontal",
    "target_segments": ["Mid-market SaaS", "Enterprise tech"],
    "pain_points": ["Slow outreach", "Low personalization"],
    "buyer_roles": ["VP of Sales", "Head of Growth"],
    "product_category": "Sales Intelligence",
    "competitive_positioning": "AI-first outreach at scale",
    "strengths": ["Fast setup", "Deep personalization"],
    "weaknesses": ["Early stage brand"],
}


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_submit_company_returns_company_id(client):
    with patch(
        "app.agents.domain_agent.DomainAgent.run",
        new_callable=AsyncMock,
    ) as mock_run:
        from app.schemas.company import CompanyAnalysis, CompanyInput, MarketType
        mock_run.return_value = CompanyAnalysis(
            company_name=SAMPLE_COMPANY["company_name"],
            market_type=MarketType.horizontal,
            **{k: v for k, v in MOCK_ANALYSIS.items() if k != "market_type"},
            raw_input=CompanyInput(**SAMPLE_COMPANY),
        )

        response = await client.post("/api/v1/company/input", json=SAMPLE_COMPANY)

    assert response.status_code == 201
    data = response.json()
    assert "company_id" in data
    assert data["status"] == "analyzed"
    assert "analysis" in data


@pytest.mark.asyncio
async def test_list_companies(client):
    response = await client.get("/api/v1/company/")
    assert response.status_code == 200
    data = response.json()
    assert "companies" in data
    assert "total" in data
