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
    """Enqueues the pipeline — falls back to BackgroundTasks if Celery fails."""
    job_id = str(uuid.uuid4())
    
    # Check if Celery is up, else fallback
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
    except Exception as exc:
        logger.warning(f"Celery unavailable ({exc}), falling back to in-memory BackgroundTasks.")
        
        # Setup local job state
        _LOCAL_JOBS[job_id] = {
            "state": "RUNNING",
            "progress": 5,
            "status": "Starting pipeline...",
            "result": None,
            "error": None
        }

        # The local background executor
        async def background_runner(jid: str, data: CompanyInput):
            # Must run inside an async context with its own DB session
            try:
                from app.pipelines.sales_pipeline import SalesPipeline
                from app.db.postgres import get_db, async_session_maker
                
                async with async_session_maker() as session:
                    _LOCAL_JOBS[jid]["status"] = "Processing stages..."
                    pipeline = SalesPipeline(
                        db=session,
                        render_js=render_js,
                        num_icps=num_icps,
                        num_personas_per_icp=num_personas_per_icp,
                    )
                    res = await pipeline.run(data)
                    await session.commit()
                    
                    _LOCAL_JOBS[jid]["state"] = "SUCCESS"
                    _LOCAL_JOBS[jid]["progress"] = 100
                    _LOCAL_JOBS[jid]["result"] = res.to_dict()
                    _LOCAL_JOBS[jid]["status"] = "Done"
            except Exception as e:
                _LOCAL_JOBS[jid]["state"] = "FAILURE"
                _LOCAL_JOBS[jid]["error"] = str(e)
                _LOCAL_JOBS[jid]["status"] = "Failed"
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
        elif state == "FAILURE":
            response["error"] = local_job.get("error")
        else:
            response["progress"] = local_job.get("progress", 0)
            response["status_msg"] = local_job.get("status", "Processing...")
            
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
