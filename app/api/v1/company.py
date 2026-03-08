"""Company Intelligence API — Module 1.

Endpoints:
  POST /v1/company/input    — submit company context, run domain analysis
  GET  /v1/company/{id}     — retrieve company + analysis
  GET  /v1/company/         — list all companies
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status, BackgroundTasks

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.db.repositories import CompanyRepository
from app.agents import DomainAgent
from app.schemas.company import CompanyInput, CompanyAnalysis

router = APIRouter(prefix="/company", tags=["Company Intelligence"])
logger = get_logger(__name__)


@router.post(
    "/input",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Submit company details and run domain intelligence analysis",
)
async def submit_company(payload: CompanyInput, db: DbSession) -> dict:
    """**Module 1** — Accepts company context and triggers domain analysis.

    Returns the company ID and analysis result.
    """
    logger.info("api.company.input", company=payload.company_name)

    # Run domain analysis
    agent = DomainAgent()
    analysis: CompanyAnalysis = await agent.run(payload)

    # Persist
    repo = CompanyRepository(db)
    record = await repo.create(
        name=payload.company_name,
        industry=payload.industry,
        input_data=payload.model_dump(mode="json"),
    )
    await repo.update_analysis(record.id, analysis.model_dump(mode="json"))

    return {
        "company_id": str(record.id),
        "status": "analyzed",
        "analysis": analysis.model_dump(mode="json"),
    }


@router.get(
    "/",
    summary="List all companies",
)
async def list_companies(db: DbSession) -> dict:
    repo = CompanyRepository(db)
    records = await repo.list_all()
    return {
        "total": len(records),
        "companies": [
            {
                "id": str(r.id),
                "name": r.name,
                "industry": r.industry,
                "created_at": r.created_at.isoformat(),
                "has_analysis": r.analysis is not None,
            }
            for r in records
        ],
    }


@router.get(
    "/{company_id}/analysis",
    summary="Get company domain analysis",
)
async def get_company_analysis(company_id: uuid.UUID, db: DbSession) -> dict:
    repo = CompanyRepository(db)
    record = await repo.get_by_id(company_id)
    if not record:
        raise HTTPException(status_code=404, detail="Company not found")
    return {
        "company_id": str(record.id),
        "name": record.name,
        "analysis": record.analysis,
        "input": record.input_data,
    }
