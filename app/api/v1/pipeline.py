"""Pipeline API — sync and async (queued) pipeline execution.

Endpoints:
  POST /pipeline/run          — submit to Celery queue (recommended for prod)
  POST /pipeline/run/sync     — run directly in the request (dev/testing)
  GET  /pipeline/status/{id}  — poll Celery job status
  GET  /pipeline/result/{id}  — get completed pipeline result
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.schemas.company import CompanyInput

router = APIRouter(prefix="/pipeline", tags=["Pipeline Orchestration"])
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Async (queued) — recommended for production
# ---------------------------------------------------------------------------


@router.post(
    "/run",
    summary="Submit pipeline to Celery queue (async)",
    description=(
        "Submits the full 8-agent pipeline as a background Celery task. "
        "Returns a **job_id** immediately. Poll `/pipeline/status/{job_id}` to track progress."
    ),
    status_code=202,
)
async def run_pipeline_async(
    payload: CompanyInput,
    render_js: bool = False,
    num_icps: int = 3,
    num_personas_per_icp: int = 2,
) -> dict:
    """Enqueues the pipeline — returns immediately with a job_id."""
    try:
        from app.workers.tasks import run_pipeline_task

        task = run_pipeline_task.apply_async(
            kwargs=dict(
                company_input_dict=payload.model_dump(mode="json"),
                render_js=render_js,
                num_icps=num_icps,
                num_personas_per_icp=num_personas_per_icp,
            )
        )
        logger.info("api.pipeline.queued", company=payload.company_name, job_id=task.id)
        return {
            "job_id": task.id,
            "status": "queued",
            "company": payload.company_name,
            "poll_url": f"/api/v1/pipeline/status/{task.id}",
            "message": "Pipeline submitted to Celery worker. Poll poll_url for updates.",
        }
    except Exception as exc:
        # Celery broker not running — tell the user clearly
        logger.error("api.pipeline.queue_error", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail=(
                f"Celery broker unavailable ({exc}). "
                "Start Redis and the Celery worker, or use POST /pipeline/run/sync for direct execution."
            ),
        )


@router.get(
    "/status/{job_id}",
    summary="Check pipeline job status",
)
async def pipeline_status(job_id: str) -> dict:
    """Poll the status of a queued pipeline job."""
    try:
        from app.workers.celery_app import celery_app

        task = celery_app.AsyncResult(job_id)
        state = task.state  # PENDING | RUNNING | SUCCESS | FAILURE | RETRY

        response: dict = {"job_id": job_id, "state": state}

        if state == "SUCCESS":
            response["result_url"] = f"/api/v1/pipeline/result/{job_id}"
            response["message"] = "Pipeline complete. Fetch result at result_url."
        elif state == "FAILURE":
            response["error"] = str(task.result)
        elif state in ("RUNNING", "STARTED"):
            meta = task.info or {}
            response["progress"] = meta.get("progress", 0)
            response["status_msg"] = meta.get("status", "Processing...")
        elif state == "PENDING":
            response["message"] = "Job is queued, waiting for a worker."

        return response
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cannot connect to Celery backend: {exc}")


@router.get(
    "/result/{job_id}",
    summary="Fetch completed pipeline result",
)
async def pipeline_result(job_id: str) -> dict:
    """Retrieve the full result of a completed pipeline job."""
    try:
        from app.workers.celery_app import celery_app

        task = celery_app.AsyncResult(job_id)
        if task.state != "SUCCESS":
            raise HTTPException(
                status_code=404,
                detail=f"Result not ready. Current state: {task.state}",
            )
        return task.result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ---------------------------------------------------------------------------
# Sync — runs directly in the FastAPI process (dev/testing only)
# ---------------------------------------------------------------------------


@router.post(
    "/run/sync",
    summary="Run pipeline synchronously (dev/testing)",
    description=(
        "Runs all 8 agents directly in the request process — **no Celery needed**. "
        "May take 60-120 seconds. Use `/run` (queued) for production."
    ),
)
async def run_pipeline_sync(
    payload: CompanyInput,
    db: DbSession,
    render_js: bool = False,
    num_icps: int = 3,
    num_personas_per_icp: int = 2,
) -> dict:
    """Execute the full pipeline in-process (blocking). Good for local dev."""
    from app.pipelines.sales_pipeline import SalesPipeline

    logger.info("api.pipeline.sync", company=payload.company_name)

    pipeline = SalesPipeline(
        db=db,
        render_js=render_js,
        num_icps=num_icps,
        num_personas_per_icp=num_personas_per_icp,
    )
    result = await pipeline.run(payload)
    return result.to_dict()
