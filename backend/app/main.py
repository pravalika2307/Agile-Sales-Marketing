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
        logger.info("SCHEDULER_ENABLED is True. Starting background campaign scheduler loop...")
        from app.core.database import SessionLocal
        from app.services.campaign_scheduler import CampaignSchedulerService
        from datetime import datetime, timezone

        async def _scheduler_loop():
            while True:
                try:
                    await asyncio.sleep(settings.SCHEDULER_INTERVAL_SECONDS)
                    db = SessionLocal()
                    try:
                        service = CampaignSchedulerService(db=db)
                        service.tick(now=datetime.now(timezone.utc))
                    finally:
                        db.close()
                except asyncio.CancelledError:
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
        logger.info("Shutting down background campaign scheduler...")
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
