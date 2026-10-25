"""Dedicated background worker entrypoint for forensic media analysis."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import Any

from rq.worker import SimpleWorker, Worker

from app.api.deps import check_redis_connectivity, get_storage
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import check_db_connectivity, close_db_engine, get_session_maker
from app.queue.connection import get_redis_sync_client
from app.queue.queue import FORENSIC_QUEUE_NAME, get_queue
from app.queue.service import AnalysisJobService

logger = logging.getLogger("ps05.worker")


class ForensicWorker:
    """Standalone background task processor for forensic media analysis."""

    def __init__(self, queue_name: str = FORENSIC_QUEUE_NAME, burst: bool = False) -> None:
        self.settings = get_settings()
        self.storage = get_storage()
        self.queue_name = queue_name
        self.burst = burst
        self._running = False
        self._worker_instance: Any = None

    async def initialize(self) -> None:
        """Verify storage directories, downstream dependencies, and run crash recovery."""
        setup_logging(
            log_level=self.settings.LOG_LEVEL,
            json_format=(self.settings.ENVIRONMENT in ("production", "staging")),
        )
        logger.info(
            "Initializing PS-05 Forensic Worker (queue=%s, burst=%s)...",
            self.queue_name,
            self.burst,
        )

        # Initialize and verify local storage vaults
        self.storage.initialize_directories()

        # Check database connectivity
        db_health = await check_db_connectivity()
        if db_health.get("status") != "HEALTHY":
            logger.warning("Worker starting with database unhealthy or unreachable: %s", db_health)
        else:
            logger.info(
                "Worker database connection verified (latency: %sms)", db_health.get("latency_ms")
            )

        # Check Redis connectivity
        redis_health = await check_redis_connectivity()
        if redis_health.get("status") != "HEALTHY":
            logger.warning("Worker starting with Redis broker unreachable: %s", redis_health)
        else:
            logger.info(
                "Worker Redis broker connection verified (latency: %sms)",
                redis_health.get("latency_ms"),
            )

        # Automatic crash recovery for jobs orphaned by previous worker termination
        await self.run_crash_recovery()

    async def run_crash_recovery(self) -> None:
        """Scan PostgreSQL for interrupted jobs stuck in PROCESSING."""
        logger.info("Checking for interrupted jobs from prior worker sessions...")
        session_factory = get_session_maker()
        async with session_factory() as session:
            service = AnalysisJobService(session)
            recovered = await service.recover_interrupted_jobs(heartbeat_timeout_seconds=60)
            if recovered:
                logger.warning("Crash recovery restored %d orphaned jobs.", len(recovered))
            else:
                logger.info("No interrupted jobs detected. State is clean.")

    def run_worker(self) -> None:
        """Run synchronous RQ worker loop."""
        conn = get_redis_sync_client()
        queue = get_queue(name=self.queue_name, connection=conn)

        # Use SimpleWorker on Windows or in burst mode to avoid os.fork() limitations
        worker_cls = SimpleWorker if (sys.platform == "win32" or self.burst) else Worker

        logger.info("Starting %s on queue '%s'...", worker_cls.__name__, self.queue_name)
        worker = worker_cls([queue], connection=conn)
        self._worker_instance = worker
        self._running = True

        try:
            worker.work(burst=self.burst, with_scheduler=True)
        except Exception as exc:
            logger.error("Error encountered in worker processing loop: %s", exc, exc_info=True)
        finally:
            self.cleanup()

    def stop(self) -> None:
        """Signal worker to stop processing and exit gracefully."""
        logger.info("Worker stop requested. Initiating graceful shutdown...")
        self._running = False
        if self._worker_instance is not None:
            # Signal worker to stop accepting new jobs
            self._worker_instance.request_stop()

    def cleanup(self) -> None:
        """Teardown database and connection resources."""
        logger.info("Tearing down worker resources...")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(close_db_engine())
            else:
                asyncio.run(close_db_engine())
        except Exception:
            pass
        logger.info("Worker shutdown completed successfully.")


def parse_arguments() -> argparse.Namespace:
    """Parse CLI options for background worker."""
    parser = argparse.ArgumentParser(description="PS-05 Forensic Task Queue Worker")
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Run in burst mode: process all available queued jobs then exit.",
    )
    parser.add_argument(
        "--queue",
        type=str,
        default=FORENSIC_QUEUE_NAME,
        help="Name of Redis queue to listen to.",
    )
    parser.add_argument(
        "--recover-only",
        action="store_true",
        help="Run crash recovery check to reconcile interrupted jobs, then exit.",
    )
    return parser.parse_args()


def main() -> None:
    """Worker process main entrypoint."""
    args = parse_arguments()
    worker = ForensicWorker(queue_name=args.queue, burst=args.burst)

    # Run async initialization & crash recovery
    asyncio.run(worker.initialize())

    if args.recover_only:
        logger.info("Crash recovery pass complete. Exiting (--recover-only).")
        return

    # Signal handlers on supported platforms
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda s, f: worker.stop())

    # Execute worker loop
    worker.run_worker()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Worker terminated by operator.")
