"""Outreach Content Generation API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.db.repositories import CompanyRepository, OutreachRepository, PersonaRepository
from app.agents import OutreachAgent
from app.schemas.company import CompanyAnalysis, CompanyInput
from app.schemas.outreach import OutreachFeedback, OutreachGenerateRequest
from app.schemas.persona import BuyerPersona

router = APIRouter(prefix="/outreach", tags=["Outreach Generation"])
logger = get_logger(__name__)


@router.post(
    "/generate",
    summary="Generate cold email, LinkedIn, and call opener for a persona",
)
async def generate_outreach(payload: OutreachGenerateRequest, db: DbSession) -> dict:
    comp_repo = CompanyRepository(db)
    record = await comp_repo.get_by_id(payload.company_id)
    if not record or not record.analysis:
        raise HTTPException(status_code=404, detail="Company not found")

    inp = CompanyInput(**record.input_data)
    analysis = CompanyAnalysis(**{**record.analysis, "raw_input": inp})

    # Find the specific persona
    persona_repo = PersonaRepository(db)
    persona_records = await persona_repo.get_by_company(payload.company_id)
    target = next(
        (r for r in persona_records if str(r.id) == str(payload.persona_id)),
        None,
    )
    if not target:
        raise HTTPException(status_code=404, detail="Persona not found")

    persona = BuyerPersona(**target.persona_data)

    assets = await OutreachAgent().run(
        persona=persona,
        analysis=analysis,
        channels=payload.channels,
        rag_collection=f"gap_{payload.company_id}",
    )

    outreach_repo = OutreachRepository(db)
    for a in assets:
        await outreach_repo.create(
            persona_id=persona.persona_id,
            company_id=payload.company_id,
            channel=a.channel,
            content=a.model_dump(mode="json"),
        )

    return {
        "company_id": str(payload.company_id),
        "persona_id": str(payload.persona_id),
        "total": len(assets),
        "outreach_assets": [a.model_dump(mode="json") for a in assets],
    }


@router.post(
    "/feedback",
    summary="Submit engagement feedback for an outreach asset",
)
async def submit_feedback(payload: OutreachFeedback, db: DbSession) -> dict:
    repo = OutreachRepository(db)
    await repo.update_feedback(
        asset_id=payload.asset_id,
        open_rate=payload.open_rate,
        reply_rate=payload.reply_rate,
        conversion_rate=payload.conversion_rate,
    )
    return {"status": "feedback_recorded", "asset_id": str(payload.asset_id)}


@router.get("/{company_id}", summary="Get outreach assets for a company")
async def get_outreach(company_id: uuid.UUID, db: DbSession) -> dict:
    repo = OutreachRepository(db)
    records = await repo.get_by_company(company_id)
    return {
        "company_id": str(company_id),
        "total": len(records),
        "assets": [r.content for r in records],
    }
