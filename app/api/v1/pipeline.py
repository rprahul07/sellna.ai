"""Pipeline API — sync and async (queued) pipeline execution.

Endpoints:
  POST /pipeline/run          — submit to Celery queue (recommended for prod)
  POST /pipeline/run/sync     — run directly in the request (dev/testing)
  GET  /pipeline/status/{id}  — poll Celery job status
  GET  /pipeline/result/{id}  — get completed pipeline result
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.schemas.company import CompanyInput

router = APIRouter(prefix="/pipeline", tags=["Pipeline Orchestration"])
logger = get_logger(__name__)

# Basic in-memory state store for async executions without celery
_LOCAL_JOBS: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Async (Internal Background Task) — modified for dual celery/fallback use
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
    background_tasks: BackgroundTasks,
    render_js: bool = False,
    num_icps: int = 3,
    num_personas_per_icp: int = 2,
) -> dict:
    """Enqueues the pipeline — falls back to BackgroundTasks if no Celery worker is available."""
    job_id = str(uuid.uuid4())

    # Check if a live Celery WORKER is available (not just a reachable broker).
    # apply_async succeeds even with no workers — tasks just queue forever.
    _celery_worker_available = False
    try:
        from app.workers.celery_app import celery_app as _celery_app
        # inspect().ping() returns {worker_id: {"ok": "pong"}} for each live worker.
        # timeout=1 so we don't block the request more than 1 second.
        active = _celery_app.control.inspect(timeout=1).ping() or {}
        _celery_worker_available = bool(active)
    except Exception:
        _celery_worker_available = False

    # Use Celery only when a worker is alive, otherwise use BackgroundTasks fallback
    if _celery_worker_available:
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
            job_id = task.id
            logger.info("api.pipeline.queued", company=payload.company_name, job_id=job_id)
            return {
                "job_id": job_id,
                "status": "queued",
                "company": payload.company_name,
                "poll_url": f"/api/v1/pipeline/status/{job_id}",
                "message": "Pipeline submitted. Poll poll_url for updates.",
            }
        except Exception as exc:
            logger.warning(f"Celery task dispatch failed ({exc}), falling back.")

    logger.warning("No Celery worker detected — using in-memory BackgroundTasks fallback.")

    # Register the job BEFORE firing the background task (prevents race condition)
    _LOCAL_JOBS[job_id] = {
        "state": "RUNNING",
        "progress": 2,
        "status_msg": "Starting pipeline...",
        "result": None,
        "error": None,
        "company_id": None,
    }

    # Progress callback — updates the shared job dict so polling works
    def make_progress_cb(jid: str):
        def on_progress(status: str, progress: int, company_id: str | None = None):
            _LOCAL_JOBS[jid]["status_msg"] = status
            _LOCAL_JOBS[jid]["progress"] = progress
            if company_id:
                _LOCAL_JOBS[jid]["company_id"] = company_id
        return on_progress

    # The local background executor
    async def background_runner(jid: str, data: CompanyInput):
        try:
            from app.pipelines.sales_pipeline import SalesPipeline
            from app.db.postgres import async_session_factory

            async with async_session_factory() as session:
                _LOCAL_JOBS[jid]["status_msg"] = "Processing stages..."
                pipeline = SalesPipeline(
                    db=session,
                    render_js=render_js,
                    num_icps=num_icps,
                    num_personas_per_icp=num_personas_per_icp,
                    on_progress=make_progress_cb(jid),
                )
                res = await pipeline.run(data)
                await session.commit()

                _LOCAL_JOBS[jid]["state"] = "SUCCESS"
                _LOCAL_JOBS[jid]["progress"] = 100
                _LOCAL_JOBS[jid]["result"] = res.to_dict()
                _LOCAL_JOBS[jid]["status_msg"] = "Done"
                if not _LOCAL_JOBS[jid]["company_id"] and res.company_id:
                    _LOCAL_JOBS[jid]["company_id"] = str(res.company_id)
        except Exception as e:
            _LOCAL_JOBS[jid]["state"] = "FAILURE"
            _LOCAL_JOBS[jid]["error"] = str(e)
            _LOCAL_JOBS[jid]["status_msg"] = "Failed"
            logger.error(f"Fallback pipeline failed: {e}")

    # Fire background task
    background_tasks.add_task(background_runner, job_id, payload)

    return {
        "job_id": job_id,
        "status": "queued",
        "company": payload.company_name,
        "poll_url": f"/api/v1/pipeline/status/{job_id}",
        "message": "Pipeline submitted. Poll poll_url for updates.",
    }




@router.get(
    "/status/{job_id}",
    summary="Check pipeline job status",
)
async def pipeline_status(job_id: str) -> dict:
    """Poll the status of a queued pipeline job."""
    # Check in local memory dictionary first
    if job_id in _LOCAL_JOBS:
        local_job = _LOCAL_JOBS[job_id]
        state = local_job["state"]
        response: dict = {"job_id": job_id, "state": state}

        if state == "SUCCESS":
            response["result_url"] = f"/api/v1/pipeline/result/{job_id}"
            response["message"] = "Pipeline complete. Fetch result at result_url."
            response["progress"] = 100
            if local_job.get("company_id"):
                response["company_id"] = local_job["company_id"]
        elif state == "FAILURE":
            response["error"] = local_job.get("error")
        else:
            response["progress"] = local_job.get("progress", 2)
            response["status_msg"] = local_job.get("status_msg", "Processing...")
            if local_job.get("company_id"):
                response["company_id"] = local_job["company_id"]

        return response

    # Fallback to celery logic
    try:
        from app.workers.celery_app import celery_app

        task = celery_app.AsyncResult(job_id)
        state = task.state  # PENDING | RUNNING | SUCCESS | FAILURE | RETRY
        logger.info("api.pipeline.status", job_id=job_id, state=state, info=str(task.info)[:200])

        response: dict = {"job_id": job_id, "state": state}

        if state == "SUCCESS":
            response["result_url"] = f"/api/v1/pipeline/result/{job_id}"
            response["message"] = "Pipeline complete. Fetch result at result_url."
        elif state == "FAILURE":
            response["error"] = str(task.result)
        elif state in ("RUNNING", "STARTED", "PROGRESS"):
            meta = task.info or {}
            response["progress"] = meta.get("progress", 0)
            response["status_msg"] = meta.get("status", "Processing...")
            if "company_id" in meta:
                response["company_id"] = meta["company_id"]
        elif state == "PENDING":
            response["message"] = "Job is queued, waiting for a worker."

        return response
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cannot connect to job backend: {exc}")


@router.post(
    "/abort/{job_id}",
    summary="Abort a running pipeline job",
)
async def abort_pipeline(job_id: str) -> dict:
    """Terminates a running or pending pipeline job."""
    if job_id in _LOCAL_JOBS:
        _LOCAL_JOBS[job_id]["state"] = "FAILURE"
        _LOCAL_JOBS[job_id]["error"] = "Aborted by user"
        return {"status": "success", "message": f"Local job {job_id} marked as failed"}

    try:
        from app.workers.celery_app import celery_app
        task = celery_app.AsyncResult(job_id)
        task.revoke(terminate=True)
        logger.info("api.pipeline.abort", job_id=job_id)
        return {"status": "success", "message": f"Job {job_id} revoked"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Failed to abort job: {exc}")


@router.get(
    "/result/{job_id}",
    summary="Fetch completed pipeline result",
)
async def pipeline_result(job_id: str) -> dict:
    """Retrieve the full result of a completed pipeline job."""
    # Check in local memory dictionary first
    if job_id in _LOCAL_JOBS:
        local_job = _LOCAL_JOBS[job_id]
        if local_job["state"] != "SUCCESS":
            raise HTTPException(
                status_code=404,
                detail=f"Result not ready. Current state: {local_job['state']}",
            )
        return local_job["result"]
        
    # Fallback to try celery
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
