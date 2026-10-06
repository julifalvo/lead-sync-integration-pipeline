"""Ingestion API: receives simulated web-form submissions and enqueues them.

This is the "source + integration edge" of the pipeline. It never talks to the
CRM or warehouse directly -- it validates, authenticates, deduplicates at the
queue boundary (idempotency key) and hands off to the worker via Redis so a
slow/failing downstream never blocks the form submitter.
"""

import redis
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from src.api.auth import require_api_key
from src.api.queue import enqueue_lead, get_redis
from src.common.config import get_settings
from src.common.db import get_conn
from src.common.logging import get_logger, log_event
from src.common.models import LeadAccepted, LeadIn

settings = get_settings()
logger = get_logger("api", settings.log_level)

app = FastAPI(
    title="Lead Sync Integration API",
    description="Webhook ingestion edge for the lead-to-warehouse integration pipeline.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    """Liveness/readiness probe used by Docker and the dashboard."""
    checks = {"postgres": False, "redis": False}
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        checks["postgres"] = True
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "health check: postgres down", level="error", error=str(exc))
    try:
        get_redis().ping()
        checks["redis"] = True
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "health check: redis down", level="error", error=str(exc))

    healthy = all(checks.values())
    status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code, content={"status": "ok" if healthy else "degraded", **checks}
    )


@app.post(
    "/webhook/leads",
    response_model=LeadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
def receive_lead(lead: LeadIn) -> LeadAccepted:
    """Accept a lead submission and enqueue it for asynchronous processing."""
    try:
        enqueue_lead(lead.model_dump(mode="json"))
    except redis.RedisError as exc:
        log_event(
            logger, "failed to enqueue lead", level="error", external_id=lead.external_id, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="queue unavailable"
        ) from exc

    log_event(logger, "lead accepted", external_id=lead.external_id, source=lead.source)
    return LeadAccepted(external_id=lead.external_id)
