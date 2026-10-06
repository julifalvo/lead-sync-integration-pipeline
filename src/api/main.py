"""Ingestion API: receives simulated web-form submissions and publishes them.

This is the "source + integration edge" of the pipeline. It never talks to the
CRM or warehouse directly -- it verifies the webhook signature, validates the
payload, and publishes to RabbitMQ (with publisher confirms) so a slow or
failing downstream never blocks the form submitter.
"""

import pika
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.api.publisher import check_broker, publish_lead
from src.api.signature import verify_signature
from src.common.config import get_settings
from src.common.db import get_conn
from src.common.logging import get_logger, log_event
from src.common.metrics import leads_ingested_total, webhook_rejections_total
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
    checks = {"postgres": False, "rabbitmq": False}
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        checks["postgres"] = True
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "health check: postgres down", level="error", error=str(exc))

    checks["rabbitmq"] = check_broker()
    if not checks["rabbitmq"]:
        log_event(logger, "health check: rabbitmq down", level="error")

    healthy = all(checks.values())
    status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code, content={"status": "ok" if healthy else "degraded", **checks}
    )


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post(
    "/webhook/leads",
    response_model=LeadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_signature)],
)
def receive_lead(lead: LeadIn) -> LeadAccepted:
    """Accept a signed lead submission and publish it for asynchronous processing."""
    try:
        publish_lead(lead.model_dump(mode="json"))
    except pika.exceptions.AMQPError as exc:
        webhook_rejections_total.labels(reason="broker_unavailable").inc()
        log_event(
            logger, "failed to publish lead", level="error", external_id=lead.external_id, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="broker unavailable"
        ) from exc

    leads_ingested_total.labels(source=lead.source).inc()
    log_event(logger, "lead accepted", external_id=lead.external_id, source=lead.source)
    return LeadAccepted(external_id=lead.external_id)
