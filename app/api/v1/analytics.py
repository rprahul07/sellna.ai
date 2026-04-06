"""Analytics & Performance API — pipeline run + optimization endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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

    # Simple weekly time series for the last 6 weeks based on asset creation time.
    now = datetime.now(timezone.utc)
    # Align to week boundaries (Monday)
    start = (now - timedelta(weeks=5)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = start - timedelta(days=start.weekday())
    buckets: dict[str, dict] = {}
    for i in range(6):
        wk = (start + timedelta(weeks=i)).date().isoformat()
        buckets[wk] = {"week_start": wk, "assets": 0, "avg_open_rate": 0.0, "avg_reply_rate": 0.0, "avg_conversion_rate": 0.0}

    # Sum then average per bucket.
    sums: dict[str, dict] = {k: {"assets": 0, "open": 0.0, "reply": 0.0, "conv": 0.0} for k in buckets.keys()}
    for r in records:
        created = r.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        wk_start = created.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=created.weekday())
        wk_key = wk_start.date().isoformat()
        if wk_key not in sums:
            continue
        sums[wk_key]["assets"] += 1
        sums[wk_key]["open"] += r.open_rate
        sums[wk_key]["reply"] += r.reply_rate
        sums[wk_key]["conv"] += r.conversion_rate

    weekly: list[dict] = []
    for wk, agg in sorted(sums.items(), key=lambda kv: kv[0]):
        n = agg["assets"]
        weekly.append(
            {
                "week_start": wk,
                "assets": n,
                "avg_open_rate": round((agg["open"] / n), 3) if n else 0.0,
                "avg_reply_rate": round((agg["reply"] / n), 3) if n else 0.0,
                "avg_conversion_rate": round((agg["conv"] / n), 3) if n else 0.0,
            }
        )

    return {
        "company_id": str(company_id),
        "total_assets": len(records),
        "by_channel": by_channel,
        "weekly": weekly,
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
