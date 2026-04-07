"""Competitor Discovery & Web Intelligence API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.db.repositories import CompanyRepository, CompetitorRepository
from app.agents import CompetitorAgent, WebAgent, CleaningAgent
from app.schemas.company import CompanyAnalysis

router = APIRouter(prefix="/competitors", tags=["Competitive Intelligence"])
logger = get_logger(__name__)


@router.post(
    "/discover/{company_id}",
    summary="Discover competitors for a company",
)
async def discover_competitors(company_id: uuid.UUID, db: DbSession) -> dict:
    """Run Competitor Discovery Agent for an existing company."""
    company_repo = CompanyRepository(db)
    record = await company_repo.get_by_id(company_id)
    if not record or not record.analysis:
        raise HTTPException(status_code=404, detail="Company or analysis not found")

    # Reconstruct analysis from stored data
    from app.schemas.company import CompanyInput
    inp = CompanyInput(**record.input_data)
    analysis = CompanyAnalysis(**{**record.analysis, "raw_input": inp})

    competitors = await CompetitorAgent().run(analysis)

    comp_repo = CompetitorRepository(db)
    await comp_repo.bulk_create(
        company_id=company_id,
        competitors=[
            {
                "competitor_id": c.competitor_id,
                "name": c.name,
                "website": c.website,
                "category": c.category,
                "positioning": c.positioning,
                "relevance_score": c.relevance_score,
            }
            for c in competitors
        ],
    )

    return {
        "company_id": str(company_id),
        "total": len(competitors),
        "competitors": [c.model_dump(mode="json") for c in competitors],
    }


@router.get(
    "/{company_id}",
    summary="Get all competitors for a company",
)
async def get_competitors(company_id: uuid.UUID, db: DbSession) -> dict:
    comp_repo = CompetitorRepository(db)
    records = await comp_repo.get_by_company(company_id)
    return {
        "company_id": str(company_id),
        "total": len(records),
        "competitors": [
            {
                "id": str(r.id),
                "name": r.name,
                "website": r.website,
                "category": r.category,
                "positioning": r.positioning,
                "relevance_score": r.relevance_score,
                "has_web_data": r.web_data is not None,
                "has_clean_data": r.clean_data is not None,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ],
    }


@router.post(
    "/scrape/{company_id}",
    summary="Scrape competitor websites and clean data",
)
async def scrape_competitors(
    company_id: uuid.UUID,
    db: DbSession,
    render_js: bool = False,
) -> dict:
    """Runs WebAgent + CleaningAgent for all discovered competitors."""
    comp_repo = CompetitorRepository(db)
    records = await comp_repo.get_by_company(company_id)
    if not records:
        raise HTTPException(status_code=404, detail="No competitors found. Run /discover first.")

    from app.schemas.competitor import CompetitorDiscovered
    competitors = [
        CompetitorDiscovered(
            competitor_id=r.id,
            name=r.name,
            website=r.website,
            category=r.category,
            positioning=r.positioning,
            relevance_score=r.relevance_score,
        )
        for r in records
    ]

    web_data = await WebAgent(render_js=render_js).run(competitors)
    clean_data = await CleaningAgent().run(web_data)

    # Update records in DB
    for wd, cd in zip(web_data, clean_data):
        await comp_repo.update_web_data(wd.competitor_id, wd.model_dump(mode="json"))
        await comp_repo.update_clean_data(cd.competitor_id, cd.model_dump(mode="json"))

    return {
        "scraped": sum(1 for w in web_data if w.scrape_success),
        "failed": sum(1 for w in web_data if not w.scrape_success),
        "competitors": [cd.model_dump(mode="json") for cd in clean_data],
    }
