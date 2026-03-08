"""ICP Generation API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.db.repositories import CompanyRepository, CompetitorRepository, ICPRepository, MarketGapRepository
from app.agents import GapAnalysisAgent, ICPAgent
from app.schemas.company import CompanyAnalysis, CompanyInput
from app.schemas.competitor import CompetitorCleanData
from app.schemas.icp import ICPGenerateRequest

router = APIRouter(prefix="/icp", tags=["ICP Generation"])
logger = get_logger(__name__)


@router.post(
    "/generate",
    summary="Generate Ideal Customer Profiles for a company",
)
async def generate_icps(payload: ICPGenerateRequest, db: DbSession) -> dict:
    company_id = payload.company_id

    # Load company analysis
    comp_repo = CompanyRepository(db)
    record = await comp_repo.get_by_id(company_id)
    if not record or not record.analysis:
        raise HTTPException(status_code=404, detail="Company analysis not found. Run /company/input first.")

    inp = CompanyInput(**record.input_data)
    analysis = CompanyAnalysis(**{**record.analysis, "raw_input": inp})

    # Load competitor clean data for RAG
    cc_repo = CompetitorRepository(db)
    comp_records = await cc_repo.get_by_company(company_id)
    clean_docs = [
        CompetitorCleanData(**(r.clean_data or {}))
        for r in comp_records
        if r.clean_data
    ]

    # Run gap analysis
    gaps = await GapAnalysisAgent().run(analysis, clean_docs)

    # Persist gaps
    gap_repo = MarketGapRepository(db)
    for gap in gaps:
        await gap_repo.create(
            company_id=company_id,
            gap_type=gap.gap_type,
            gap_data=gap.model_dump(mode="json"),
            confidence=gap.confidence_score,
        )

    # Generate ICPs
    icps = await ICPAgent().run(analysis, gaps, payload.num_profiles)

    icp_repo = ICPRepository(db)
    for icp in icps:
        await icp_repo.create(company_id=company_id, profile_data=icp.model_dump(mode="json"))

    return {
        "company_id": str(company_id),
        "icps": [i.model_dump(mode="json") for i in icps],
        "market_gaps": [g.model_dump(mode="json") for g in gaps],
    }


@router.get(
    "/{company_id}",
    summary="Get generated ICPs for a company",
)
async def get_icps(company_id: uuid.UUID, db: DbSession) -> dict:
    repo = ICPRepository(db)
    records = await repo.get_by_company(company_id)
    return {
        "company_id": str(company_id),
        "total": len(records),
        "icps": [r.profile_data for r in records],
    }
