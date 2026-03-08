"""Analytics & Performance API — pipeline run + optimization endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.db.repositories import OutreachRepository
from app.agents import OptimizationAgent
from app.schemas.outreach import OutreachAsset, OutreachFeedback

router = APIRouter(prefix="/analytics", tags=["Analytics"])
logger = get_logger(__name__)


@router.get(
    "/performance/{company_id}",
    summary="Get outreach performance analytics for a company",
)
async def get_performance(company_id: uuid.UUID, db: DbSession) -> dict:
    repo = OutreachRepository(db)
    records = await repo.get_by_company(company_id)
    if not records:
        raise HTTPException(status_code=404, detail="No outreach data found")

    by_channel: dict[str, dict] = {}
    for r in records:
        ch = r.channel
        if ch not in by_channel:
            by_channel[ch] = {"count": 0, "open_rate": 0.0, "reply_rate": 0.0, "conversion_rate": 0.0}
        by_channel[ch]["count"] += 1
        by_channel[ch]["open_rate"] += r.open_rate
        by_channel[ch]["reply_rate"] += r.reply_rate
        by_channel[ch]["conversion_rate"] += r.conversion_rate

    # Average rates
    for ch, stats in by_channel.items():
        n = stats["count"]
        stats["avg_open_rate"] = round(stats.pop("open_rate") / n, 3)
        stats["avg_reply_rate"] = round(stats.pop("reply_rate") / n, 3)
        stats["avg_conversion_rate"] = round(stats.pop("conversion_rate") / n, 3)

    return {
        "company_id": str(company_id),
        "total_assets": len(records),
        "by_channel": by_channel,
    }


@router.post(
    "/optimize/{company_id}",
    summary="Run Optimization Agent to improve targeting and messaging",
)
async def optimize(company_id: uuid.UUID, db: DbSession) -> dict:
    repo = OutreachRepository(db)
    records = await repo.get_by_company(company_id)
    if not records:
        raise HTTPException(status_code=404, detail="No outreach assets found")

    assets = [OutreachAsset(**r.content) for r in records]
    feedback = [
        OutreachFeedback(
            asset_id=r.id,
            open_rate=r.open_rate,
            reply_rate=r.reply_rate,
            conversion_rate=r.conversion_rate,
        )
        for r in records
    ]

    recommendations = await OptimizationAgent().run(assets, feedback)
    return {
        "company_id": str(company_id),
        "recommendations": recommendations,
    }
