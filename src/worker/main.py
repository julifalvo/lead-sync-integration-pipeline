"""Worker: consumes the leads queue, transforms, loads CRM + warehouse.

Reliability features demonstrated here:
  - Retries with exponential backoff (tenacity) around the flaky CRM call.
  - Dead-lettering: once retries are exhausted the message is nacked without
    requeue, which RabbitMQ routes to `leads.dlq` via the queue's
    `x-dead-letter-exchange` (see src/common/broker.py) instead of being
    silently dropped or retried forever.
  - Idempotency: both `crm.leads` and `warehouse.leads` have a UNIQUE
    constraint on `external_id`, and every write is an upsert, so replaying
    the same message (e.g. a redelivery after a worker crash, or a duplicate
    webhook delivery) never creates a duplicate row.
  - Structured JSON logs plus a `warehouse.integration_events` audit trail
    that the dashboard reads to show recent successes/errors, and Prometheus
    metrics on :9100/metrics for Grafana.
"""

import json
import time

import pika
from prometheus_client import start_http_server
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.common.broker import declare_topology, get_connection
from src.common.config import get_settings
from src.common.db import get_conn
from src.common.logging import get_logger, log_event
from src.common.metrics import (
    crm_retry_attempts_total,
    lead_processing_seconds,
    leads_dead_lettered_total,
    leads_processed_total,
)
from src.worker.crm import CrmUnavailableError
from src.worker.crm import upsert_lead as crm_upsert
from src.worker.transform import to_crm_record, to_warehouse_record
from src.worker.warehouse import log_event as record_event
from src.worker.warehouse import record_raw_event
from src.worker.warehouse import upsert_lead as warehouse_upsert

settings = get_settings()
logger = get_logger("worker", settings.log_level)


class ProcessingFailed(Exception):
    """Raised when a message could not be processed and should be dead-lettered."""


@retry(
    retry=retry_if_exception_type(CrmUnavailableError),
    wait=wait_exponential(multiplier=0.5, max=8),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _crm_upsert_with_retry(conn, record: dict) -> bool:
    crm_retry_attempts_total.inc()
    return crm_upsert(conn, record)


@lead_processing_seconds.time()
def process_message(raw_message: bytes) -> None:
    lead = json.loads(raw_message)
    external_id = lead["external_id"]
    crm_record = to_crm_record(lead)

    with get_conn() as conn:
        record_raw_event(conn, external_id, lead.get("source", "webform"), lead)
        try:
            is_new = _crm_upsert_with_retry(conn, crm_record)
        except CrmUnavailableError as exc:
            record_event(conn, external_id, "error", f"dead-lettered after retries: {exc}")
            leads_dead_lettered_total.inc()
            log_event(
                logger,
                "lead dead-lettered: CRM retries exhausted",
                level="error",
                external_id=external_id,
                error=str(exc),
            )
            raise ProcessingFailed(str(exc)) from exc

        warehouse_record = to_warehouse_record(crm_record)
        warehouse_upsert(conn, warehouse_record)
        outcome = "inserted" if is_new else "updated (duplicate replay)"
        record_event(conn, external_id, "success", outcome)
        leads_processed_total.labels(outcome="new" if is_new else "duplicate_replay").inc()
        log_event(logger, "lead synced", external_id=external_id, new_record=is_new)


def _on_message(channel, method, _properties, body: bytes) -> None:
    try:
        process_message(body)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except ProcessingFailed:
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception:  # noqa: BLE001 -- any other bug must not wedge the queue either
        log_event(logger, "unexpected error processing message, dead-lettering", level="error")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def run_forever() -> None:
    start_http_server(settings.worker_metrics_port)
    connection = get_connection()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=10)
    channel.basic_consume(queue=settings.queue_name, on_message_callback=_on_message)

    log_event(logger, "worker started", queue=settings.queue_name, metrics_port=settings.worker_metrics_port)
    try:
        channel.start_consuming()
    except (KeyboardInterrupt, pika.exceptions.ConnectionClosedByBroker):
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    # small startup delay so docker-compose dependencies (postgres/rabbitmq) are ready
    time.sleep(2)
    run_forever()
