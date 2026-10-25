"""RQ Queue instantiation and management."""

from __future__ import annotations

import logging
from typing import Any

from rq import Queue

from app.queue.connection import get_redis_sync_client

logger = logging.getLogger("ps05.queue")

FORENSIC_QUEUE_NAME = "forensic_analysis"


def get_queue(
    name: str = FORENSIC_QUEUE_NAME,
    connection: Any | None = None,
    is_async: bool = True,
) -> Queue:
    """
    Return RQ Queue instance with configured connection.
    `is_async=False` can be used in testing to execute jobs synchronously inline.
    """
    conn = connection or get_redis_sync_client()
    return Queue(name=name, connection=conn, is_async=is_async)


def get_queue_stats(
    name: str = FORENSIC_QUEUE_NAME,
    connection: Any | None = None,
) -> dict[str, int]:
    """Inspect queue depth and job counts."""
    q = get_queue(name=name, connection=connection)
    return {
        "queued_jobs": len(q),
        "started_jobs": q.started_job_registry.count,
        "failed_jobs": q.failed_job_registry.count,
        "finished_jobs": q.finished_job_registry.count,
    }
