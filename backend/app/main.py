"""Agile Sales & Marketing - Backend Application Entrypoint."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings

# Setup basic logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agile_sales_marketing")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager starting the background scheduler loop when enabled."""
    scheduler_task = None
    graph_sync_task = None

    if settings.SCHEDULER_ENABLED:
        logger.info(
            "SCHEDULER_ENABLED is True. Starting background campaign scheduler loop "
            "(interval=%ds, auto_dispatch=%s, batch_size=%d)...",
            settings.SCHEDULER_INTERVAL_SECONDS,
            settings.SCHEDULER_AUTO_DISPATCH,
            settings.SCHEDULER_BATCH_SIZE,
        )
        from app.core.database import SessionLocal
        from app.services.campaign_scheduler import CampaignSchedulerService
        from datetime import datetime, timezone

        async def _scheduler_loop():
            # Initial grace period on startup before the first tick (e.g. 2s for DB pool readiness)
            # Promptly recovers any overdue steps from previous downtime without waiting a full interval
            initial_delay = min(2, settings.SCHEDULER_INTERVAL_SECONDS)
            try:
                await asyncio.sleep(initial_delay)
            except asyncio.CancelledError:
                return

            logger.info("Executing initial campaign scheduler recovery tick on startup...")
            try:
                db = SessionLocal()
                try:
                    service = CampaignSchedulerService(db=db)
                    init_res = service.tick(
                        now=datetime.now(timezone.utc),
                        auto_dispatch=True,
                    )
                    logger.info("Initial scheduler recovery tick completed: %s", init_res.message)
                finally:
                    db.close()
            except Exception as exc:
                logger.error("Error during initial scheduler recovery tick: %s", exc)

            while True:
                try:
                    await asyncio.sleep(settings.SCHEDULER_INTERVAL_SECONDS)
                    db = SessionLocal()
                    try:
                        service = CampaignSchedulerService(db=db)
                        service.tick(
                            now=datetime.now(timezone.utc),
                            auto_dispatch=True,
                        )
                    finally:
                        db.close()
                except asyncio.CancelledError:
                    logger.info("Background campaign scheduler loop cancelled.")
                    break
                except Exception as exc:
                    logger.error("Error in background campaign scheduler loop: %s", exc)

        scheduler_task = asyncio.create_task(_scheduler_loop())
    else:
        logger.info("Campaign scheduler is disabled by default (settings.SCHEDULER_ENABLED is False).")

    if settings.is_graph_auto_sync_allowed:
        logger.info("Microsoft Graph auto-sync is enabled. Starting background mailbox sync loop...")
        from app.services.graph.scheduler import run_graph_auto_sync_loop
        graph_sync_task = asyncio.create_task(run_graph_auto_sync_loop())
    else:
        logger.info("Microsoft Graph auto-sync is disabled by safety guards (is_graph_auto_sync_allowed is False).")

    yield

    if scheduler_task:
        logger.info("Shutting down background campaign scheduler cleanly...")
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

    if graph_sync_task:
        logger.info("Shutting down background Microsoft Graph auto-sync loop...")
        graph_sync_task.cancel()
        try:
            await graph_sync_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for Agile Sales & Marketing platform.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration: strict allowlist restricting cross-origin credentialed access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-Total-Count",
        "x-retell-signature",
        "X-Webhook-Secret",
        "X-Twilio-Signature",
    ],
    expose_headers=["X-Total-Count"],
)

# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Health"])
async def root():
    """Root status endpoint."""
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Application health probe."""
    return {
        "status": "ok",
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "hubspot_configured": settings.is_hubspot_configured,
    }
