"""Celery tasks — long-running Sales AI operations.

Tasks:
  run_pipeline_task   — full 8-agent pipeline
  run_outreach_task   — generate outreach for a single persona

Each task runs the async pipeline inside asyncio.run() because
Celery workers are synchronous by default.
Results are stored in Redis (via celery backend) and retrievable
by job_id from the /pipeline/status/{job_id} endpoint.
"""

from __future__ import annotations

import asyncio
import traceback

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)
_s = get_settings()


def _get_session() -> AsyncSession:
    """Create a fresh async DB session inside the Celery worker process."""
    engine = create_async_engine(_s.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory()


# ---------------------------------------------------------------------------
# Task: Full Pipeline
# ---------------------------------------------------------------------------


@celery_app.task(
    name="sales_ai.run_pipeline",
    bind=True,
    max_retries=1,
    soft_time_limit=3600,  # 60 min soft kill
    time_limit=3800,       # hard kill
)
def run_pipeline_task(
    self,
    company_input_dict: dict,
    render_js: bool = False,
    num_icps: int = 1,
    num_personas_per_icp: int = 1,
) -> dict:
    """Run the full Sales AI pipeline as a background Celery task.

    Returns the PipelineResult dict which is stored in Redis.
    """
    from app.pipelines.sales_pipeline import SalesPipeline
    from app.schemas.company import CompanyInput

    logger.info("celery.pipeline.start", task_id=self.request.id)

    # Update task state so API can report progress
    self.update_state(state="RUNNING", meta={"status": "Pipeline started", "progress": 0})

    async def _run():
        def on_prog(status, progress, company_id=None):
            logger.info("pipeline.progress", status=status, progress=progress, company_id=company_id)
            meta = {"status": status, "progress": progress}
            if company_id:
                meta["company_id"] = company_id
            self.update_state(state="RUNNING", meta=meta)

        async with _get_session() as session:
            try:
                payload = CompanyInput(**company_input_dict)
                pipeline = SalesPipeline(
                    db=session,
                    render_js=render_js,
                    num_icps=num_icps,
                    num_personas_per_icp=num_personas_per_icp,
                    on_progress=on_prog,
                )
                res = await pipeline.run(payload)
                await session.commit()
                return res
            except Exception as e:
                await session.rollback()
                logger.error(f"Pipeline DB session failed: {e}")
                raise

    try:
        result = asyncio.run(_run())
        logger.info(
            "celery.pipeline.complete",
            task_id=self.request.id,
            duration=result.duration_seconds,
            errors=len(result.errors),
        )
        return result.to_dict()
    except Exception as exc:
        logger.error(
            "celery.pipeline.failed",
            task_id=self.request.id,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise self.retry(exc=exc, countdown=30)  # retry once after 30s


# ---------------------------------------------------------------------------
# Task: Single Outreach Generation
# ---------------------------------------------------------------------------


@celery_app.task(
    name="sales_ai.run_outreach",
    bind=True,
    max_retries=2,
    soft_time_limit=1800,
    time_limit=2000,
)
def run_outreach_task(
    self,
    company_id: str,
    persona_id: str,
    channels: list[str] | None = None,
) -> dict:
    """Generate outreach content for a single persona as a background task."""
    from app.agents import OutreachAgent
    from app.db.repositories import CompanyRepository, PersonaRepository
    from app.schemas.company import CompanyAnalysis, CompanyInput
    from app.schemas.persona import BuyerPersona

    logger.info("celery.outreach.start", task_id=self.request.id, persona_id=persona_id)

    async def _run():
        async with _get_session() as session:
            company_repo = CompanyRepository(session)
            record = await company_repo.get_by_id(company_id)
            inp = CompanyInput(**record.input_data)
            analysis = CompanyAnalysis(**{**record.analysis, "raw_input": inp})

            persona_repo = PersonaRepository(session)
            persona_records = await persona_repo.get_by_company(company_id)
            target = next((r for r in persona_records if str(r.id) == persona_id), None)
            if not target:
                raise ValueError(f"Persona {persona_id} not found")

            persona = BuyerPersona(**target.persona_data)
            agent = OutreachAgent()
            assets = await agent.run(
                persona=persona,
                analysis=analysis,
                channels=channels,
                rag_collection=f"gap_{company_id}",
            )
            return {"assets": [a.model_dump(mode="json") for a in assets]}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("celery.outreach.failed", task_id=self.request.id, error=str(exc))
        raise self.retry(exc=exc, countdown=10)
