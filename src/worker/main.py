"""Worker: consumes the leads queue, transforms, loads CRM + warehouse.

Reliability features demonstrated here:
  - Retries with exponential backoff (tenacity) around the flaky CRM call.
  - Idempotency: both `crm.leads` and `warehouse.leads` have a UNIQUE
    constraint on `external_id`, and every write is an upsert, so replaying
    the same message (e.g. after a retry, or a duplicate webhook delivery)
    never creates a duplicate row.
  - Structured JSON logs plus a `warehouse.integration_events` audit trail
    that the dashboard reads to show recent successes/errors.
"""

import json
import time

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.api.queue import get_redis
from src.common.config import get_settings
from src.common.db import get_conn
from src.common.logging import get_logger, log_event
from src.worker.crm import CrmUnavailableError
from src.worker.crm import upsert_lead as crm_upsert
from src.worker.transform import to_crm_record, to_warehouse_record
from src.worker.warehouse import log_event as record_event
from src.worker.warehouse import upsert_lead as warehouse_upsert

settings = get_settings()
logger = get_logger("worker", settings.log_level)


@retry(
    retry=retry_if_exception_type(CrmUnavailableError),
    wait=wait_exponential(multiplier=0.5, max=8),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _crm_upsert_with_retry(conn, record: dict) -> bool:
    return crm_upsert(conn, record)


def process_message(raw_message: str) -> None:
    lead = json.loads(raw_message)
    external_id = lead["external_id"]
    crm_record = to_crm_record(lead)

    with get_conn() as conn:
        try:
            is_new = _crm_upsert_with_retry(conn, crm_record)
            warehouse_record = to_warehouse_record(crm_record)
            warehouse_upsert(conn, warehouse_record)
            record_event(conn, external_id, "success", "inserted" if is_new else "updated (duplicate replay)")
            log_event(logger, "lead synced", external_id=external_id, new_record=is_new)
        except CrmUnavailableError as exc:
            record_event(conn, external_id, "error", str(exc))
            log_event(
                logger,
                "lead sync failed after retries",
                level="error",
                external_id=external_id,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            record_event(conn, external_id, "error", str(exc))
            log_event(
                logger,
                "unexpected error processing lead",
                level="error",
                external_id=external_id,
                error=str(exc),
            )


def run_forever() -> None:
    redis_client = get_redis()
    log_event(logger, "worker started", queue=settings.queue_name)
    while True:
        item = redis_client.blpop(settings.queue_name, timeout=5)
        if item is None:
            continue
        _, raw_message = item
        process_message(raw_message)


if __name__ == "__main__":
    # small startup delay so docker-compose dependencies (postgres/redis) are ready
    time.sleep(2)
    run_forever()
