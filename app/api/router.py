"""Central API router — mounts all v1 sub-routers."""

from fastapi import APIRouter

from app.api.v1 import company, competitors, icp, personas, outreach, analytics, pipeline

api_router = APIRouter()

api_router.include_router(company.router)
api_router.include_router(competitors.router)
api_router.include_router(icp.router)
api_router.include_router(personas.router)
api_router.include_router(outreach.router)
api_router.include_router(analytics.router)
api_router.include_router(pipeline.router)
