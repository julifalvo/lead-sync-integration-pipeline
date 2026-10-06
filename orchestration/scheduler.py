"""Minimal in-house scheduler, documented as a deliberate alternative to Airflow.

Why not Airflow/Prefect here: the pipeline is a single, always-on streaming
hop (webhook -> queue -> worker), not a batch DAG with branching dependencies.
A scheduler container that *periodically* re-checks pipeline health and emits
a heartbeat event is enough to demonstrate orchestration without the
operational weight of a full DAG engine. See ARCHITECTURE.md for the
trade-off discussion and how this would be swapped for Airflow if the
pipeline grew batch stages (e.g. nightly dedup/reconciliation jobs).
"""

import time

import requests
from apscheduler.schedulers.blocking import BlockingScheduler

from src.common.config import get_settings
from src.common.db import get_conn
from src.common.logging import get_logger, log_event

settings = get_settings()
logger = get_logger("scheduler", settings.log_level)

API_HEALTH_URL = "http://api:8000/health"


def heartbeat_job() -> None:
    try:
        resp = requests.get(API_HEALTH_URL, timeout=5)
        log_event(logger, "heartbeat", api_status=resp.status_code)
    except requests.RequestException as exc:
        log_event(logger, "heartbeat failed", level="error", error=str(exc))


def reconcile_job() -> None:
    """Nightly-style batch job: flags leads present in the CRM but missing from the warehouse."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.external_id FROM crm.leads c
            LEFT JOIN warehouse.leads w ON w.external_id = c.external_id
            WHERE w.external_id IS NULL
            """
        ).fetchall()
        if rows:
            log_event(logger, "reconciliation gap detected", level="warning", missing_count=len(rows))
        else:
            log_event(logger, "reconciliation ok", missing_count=0)


def main() -> None:
    time.sleep(5)
    scheduler = BlockingScheduler()
    scheduler.add_job(heartbeat_job, "interval", seconds=30, id="heartbeat")
    scheduler.add_job(reconcile_job, "interval", minutes=5, id="reconcile")
    log_event(logger, "scheduler started")
    scheduler.start()


if __name__ == "__main__":
    main()
