import asyncio, json
from app.db.postgres import async_session_factory, OutreachRecord
from sqlalchemy import select

async def main():
    async with async_session_factory() as session:
        out = await session.execute(select(OutreachRecord))
        data = [{"id": str(r.id), "company_id": str(r.company_id)} for r in out.scalars().all()]
        with open("out_db.json", "w") as f:
            json.dump(data, f, indent=2)

asyncio.run(main())
