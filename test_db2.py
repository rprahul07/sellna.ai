import asyncio
from app.db.postgres import async_session_factory, OutreachRecord
from sqlalchemy import select

async def main():
    async with async_session_factory() as session:
        out = await session.execute(select(OutreachRecord))
        for r in out.scalars().all():
            print(f"Asset ID: {r.id}, Company ID: {r.company_id}")

asyncio.run(main())
