import asyncio
from app.db.postgres import async_session_factory, OutreachRecord, PersonaRecord, ICPRecord, CompetitorRecord
from sqlalchemy import select

async def main():
    async with async_session_factory() as session:
        out = await session.execute(select(OutreachRecord))
        per = await session.execute(select(PersonaRecord))
        icp = await session.execute(select(ICPRecord))
        com = await session.execute(select(CompetitorRecord))
        
        print("Outreaches:", len(out.scalars().all()))
        print("Personas:", len(per.scalars().all()))
        print("ICPs:", len(icp.scalars().all()))
        print("Competitors:", len(com.scalars().all()))

asyncio.run(main())
