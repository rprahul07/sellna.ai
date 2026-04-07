"""Repository layer — typed CRUD wrappers over SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import (
    CompanyRecord,
    CompetitorRecord,
    ICPRecord,
    MarketGapRecord,
    OutreachRecord,
    PersonaRecord,
)


# ---------------------------------------------------------------------------
# Company Repository
# ---------------------------------------------------------------------------


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create(self, name: str, industry: str, input_data: dict, company_id: Optional[uuid.UUID] = None) -> CompanyRecord:
        record = CompanyRecord(id=company_id or uuid.uuid4(), name=name, industry=industry, input_data=input_data)
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_by_id(self, company_id: uuid.UUID) -> Optional[CompanyRecord]:
        result = await self._db.execute(select(CompanyRecord).where(CompanyRecord.id == company_id))
        return result.scalar_one_or_none()

    async def update_analysis(self, company_id: uuid.UUID, analysis: dict) -> None:
        record = await self.get_by_id(company_id)
        if record:
            record.analysis = analysis
            await self._db.flush()

    async def list_all(self) -> list[CompanyRecord]:
        result = await self._db.execute(select(CompanyRecord).order_by(CompanyRecord.created_at.desc()))
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Competitor Repository
# ---------------------------------------------------------------------------


class CompetitorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def bulk_create(self, company_id: uuid.UUID, competitors: list[dict]) -> list[CompetitorRecord]:
        records = [
            CompetitorRecord(
                id=c.get("competitor_id") or uuid.uuid4(),
                company_id=company_id,
                name=c.get("name"),
                website=c.get("website"),
                category=c.get("category"),
                positioning=c.get("positioning"),
                relevance_score=c.get("relevance_score", 0.0)
            ) 
            for c in competitors
        ]
        self._db.add_all(records)
        await self._db.flush()
        return records

    async def get_by_company(self, company_id: uuid.UUID) -> list[CompetitorRecord]:
        result = await self._db.execute(
            select(CompetitorRecord).where(CompetitorRecord.company_id == company_id)
        )
        return list(result.scalars().all())

    async def update_web_data(self, competitor_id: uuid.UUID, web_data: dict) -> None:
        result = await self._db.execute(
            select(CompetitorRecord).where(CompetitorRecord.id == competitor_id)
        )
        record = result.scalar_one_or_none()
        if record:
            record.web_data = web_data
            await self._db.flush()

    async def update_clean_data(self, competitor_id: uuid.UUID, clean_data: dict) -> None:
        result = await self._db.execute(
            select(CompetitorRecord).where(CompetitorRecord.id == competitor_id)
        )
        record = result.scalar_one_or_none()
        if record:
            record.clean_data = clean_data
            await self._db.flush()


# ---------------------------------------------------------------------------
# ICP Repository
# ---------------------------------------------------------------------------


class ICPRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create(self, company_id: uuid.UUID, profile_data: dict, icp_id: Optional[uuid.UUID] = None) -> ICPRecord:
        record = ICPRecord(id=icp_id or uuid.uuid4(), company_id=company_id, profile_data=profile_data)
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_by_company(self, company_id: uuid.UUID) -> list[ICPRecord]:
        result = await self._db.execute(
            select(ICPRecord).where(ICPRecord.company_id == company_id)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Persona Repository
# ---------------------------------------------------------------------------


class PersonaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create(self, icp_id: uuid.UUID, company_id: uuid.UUID, persona_data: dict, persona_id: Optional[uuid.UUID] = None) -> PersonaRecord:
        record = PersonaRecord(id=persona_id or uuid.uuid4(), icp_id=icp_id, company_id=company_id, persona_data=persona_data)
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_by_company(self, company_id: uuid.UUID) -> list[PersonaRecord]:
        result = await self._db.execute(
            select(PersonaRecord).where(PersonaRecord.company_id == company_id)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Outreach Repository
# ---------------------------------------------------------------------------


class OutreachRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create(
        self,
        persona_id: uuid.UUID,
        company_id: uuid.UUID,
        channel: str,
        content: dict,
        asset_id: Optional[uuid.UUID] = None,
    ) -> OutreachRecord:
        record = OutreachRecord(
            id=asset_id or uuid.uuid4(),
            persona_id=persona_id,
            company_id=company_id,
            channel=channel,
            content=content
        )
        self._db.add(record)
        await self._db.flush()
        return record

    async def update_feedback(
        self,
        asset_id: uuid.UUID,
        open_rate: float,
        reply_rate: float,
        conversion_rate: float,
    ) -> None:
        result = await self._db.execute(
            select(OutreachRecord).where(OutreachRecord.id == asset_id)
        )
        record = result.scalar_one_or_none()
        if record:
            record.open_rate = open_rate
            record.reply_rate = reply_rate
            record.conversion_rate = conversion_rate
            await self._db.flush()

    async def seed_feedback(self, company_id: uuid.UUID) -> None:
        """Seeds realistic, semi-random engagement data for a pipeline run demo."""
        import random
        result = await self._db.execute(
            select(OutreachRecord).where(OutreachRecord.company_id == company_id)
        )
        records = result.scalars().all()
        for r in records:
            # Generate semi-realistic rates based on channel
            if r.channel == "cold_email":
                r.open_rate = random.uniform(0.15, 0.45)
                r.reply_rate = random.uniform(0.01, 0.08)
                r.conversion_rate = random.uniform(0.002, 0.02)
            elif r.channel == "linkedin":
                r.open_rate = 1.0  # LinkedIn messages are usually 'opened' if seen
                r.reply_rate = random.uniform(0.05, 0.22)
                r.conversion_rate = random.uniform(0.01, 0.05)
            else:
                r.open_rate = random.uniform(0.3, 0.6)
                r.reply_rate = random.uniform(0.02, 0.12)
                r.conversion_rate = random.uniform(0.01, 0.04)
        await self._db.flush()

    async def get_by_company(self, company_id: uuid.UUID) -> list[OutreachRecord]:
        result = await self._db.execute(
            select(OutreachRecord).where(OutreachRecord.company_id == company_id)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Market Gap Repository
# ---------------------------------------------------------------------------


class MarketGapRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create(self, company_id: uuid.UUID, gap_type: str, gap_data: dict, confidence: float, gap_id: Optional[uuid.UUID] = None) -> MarketGapRecord:
        record = MarketGapRecord(
            id=gap_id or uuid.uuid4(),
            company_id=company_id, 
            gap_type=gap_type, 
            gap_data=gap_data, 
            confidence_score=confidence
        )
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_by_company(self, company_id: uuid.UUID) -> list[MarketGapRecord]:
        result = await self._db.execute(
            select(MarketGapRecord).where(MarketGapRecord.company_id == company_id)
        )
        return list(result.scalars().all())
