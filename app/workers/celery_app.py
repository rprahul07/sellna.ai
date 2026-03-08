"""Celery application instance.

Worker startup:
    celery -A app.workers.celery_app worker --loglevel=info --concurrency=2

Beat scheduler (optional, for periodic tasks):
    celery -A app.workers.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

_s = get_settings()

celery_app = Celery(
    "sales_ai",
    broker=_s.celery_broker_url,
    backend=_s.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task behaviour
    task_track_started=True,
    task_acks_late=True,            # re-queue on worker crash
    worker_prefetch_multiplier=1,   # one task at a time per worker slot (pipeline is heavy)
    # Result expiry — keep results for 24 h then auto-delete from Redis
    result_expires=86_400,
    # Retries
    task_max_retries=2,
    task_default_retry_delay=30,
)
