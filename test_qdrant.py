import asyncio
import qdrant_client
from qdrant_client import models

async def main():
    try:
        client = qdrant_client.AsyncQdrantClient(':memory:')
        await client.create_collection('test', vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
        await client.upsert('test', points=[models.PointStruct(id=1, vector=[0.5, 0.5])])
        res = await client.query_points('test', query=[0.5, 0.5])
        print("QUERY POINTS:", res.points[0].id)
    except Exception as e:
        print("ERROR:", e)

asyncio.run(main())
