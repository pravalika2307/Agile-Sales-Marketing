"""Standalone Campaign Execution Scheduler Worker CLI."""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.campaign_scheduler import CampaignSchedulerService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("campaign_scheduler_worker")

_should_exit = False


def _signal_handler(sig, frame):
    global _should_exit
    logger.info("Received termination signal %s. Shutting down worker gracefully...", sig)
    _should_exit = True


def run_scheduler_tick(dry_run: bool = False, force: bool = False, auto_dispatch: bool = False) -> None:
    """Execute a single scheduler evaluation tick."""
    db = SessionLocal()
    try:
        service = CampaignSchedulerService(db=db)
        result = service.tick(
            now=datetime.now(timezone.utc),
            dry_run=dry_run,
            auto_dispatch=auto_dispatch,
            force=force,
        )
        if result.status == "disabled":
            logger.info("Scheduler tick skipped: %s", result.message)
        else:
            logger.info(
                "Scheduler tick completed: %s (planned: %d, completed: %d, halted: %d, skipped: %d, errors: %d)",
                "DRY-RUN" if result.dry_run else "EXECUTED",
                result.planned_count,
                result.completed_count,
                result.halted_count,
                result.skipped_count,
                result.error_count,
            )
    except Exception as exc:
        logger.error("Error during scheduler tick: %s", exc, exc_info=True)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Agile Sales & Marketing Campaign Scheduler Worker")
    parser.add_argument("--once", action="store_true", help="Run a single scheduler tick and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (zero database writes or external calls).")
    parser.add_argument("--force", action="store_true", help="Force execution even if SCHEDULER_ENABLED is False.")
    parser.add_argument("--auto-dispatch", action="store_true", help="Also dispatch scheduled outreach when due.")
    parser.add_argument("--interval", type=int, default=settings.SCHEDULER_INTERVAL_SECONDS, help="Polling interval in seconds.")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info(
        "Starting Campaign Scheduler Worker (interval=%ds, dry_run=%s, scheduler_enabled=%s)",
        args.interval,
        args.dry_run,
        settings.SCHEDULER_ENABLED,
    )

    if args.once:
        run_scheduler_tick(dry_run=args.dry_run, force=args.force, auto_dispatch=args.auto_dispatch)
        logger.info("Single tick completed. Worker exiting.")
        return

    while not _should_exit:
        run_scheduler_tick(dry_run=args.dry_run, force=args.force, auto_dispatch=args.auto_dispatch)
        sleep_elapsed = 0
        while sleep_elapsed < args.interval and not _should_exit:
            time.sleep(1)
            sleep_elapsed += 1

    logger.info("Scheduler worker exited cleanly.")


if __name__ == "__main__":
    main()
