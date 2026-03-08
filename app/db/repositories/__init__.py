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

    async def create(self, name: str, industry: str, input_data: dict) -> CompanyRecord:
        record = CompanyRecord(name=name, industry=industry, input_data=input_data)
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
        records = [CompetitorRecord(company_id=company_id, **c) for c in competitors]
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

    async def create(self, company_id: uuid.UUID, profile_data: dict) -> ICPRecord:
        record = ICPRecord(company_id=company_id, profile_data=profile_data)
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

    async def create(self, icp_id: uuid.UUID, company_id: uuid.UUID, persona_data: dict) -> PersonaRecord:
        record = PersonaRecord(icp_id=icp_id, company_id=company_id, persona_data=persona_data)
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
    ) -> OutreachRecord:
        record = OutreachRecord(
            persona_id=persona_id, company_id=company_id, channel=channel, content=content
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

    async def create(self, company_id: uuid.UUID, gap_type: str, gap_data: dict, confidence: float) -> MarketGapRecord:
        record = MarketGapRecord(
            company_id=company_id, gap_type=gap_type, gap_data=gap_data, confidence_score=confidence
        )
        self._db.add(record)
        await self._db.flush()
        return record

    async def get_by_company(self, company_id: uuid.UUID) -> list[MarketGapRecord]:
        result = await self._db.execute(
            select(MarketGapRecord).where(MarketGapRecord.company_id == company_id)
        )
        return list(result.scalars().all())
