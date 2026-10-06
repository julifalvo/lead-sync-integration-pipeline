"""Warehouse load: idempotent upsert into the analytics-facing schema."""

import json

from psycopg import Connection


def record_raw_event(conn: Connection, external_id: str, source: str, payload: dict) -> None:
    """Bronze layer: log the message verbatim, before any transform or CRM call."""
    conn.execute(
        """
        INSERT INTO warehouse.raw_lead_events (external_id, source, payload)
        VALUES (%(external_id)s, %(source)s, %(payload)s)
        """,
        {"external_id": external_id, "source": source, "payload": json.dumps(payload)},
    )


def upsert_lead(conn: Connection, record: dict) -> None:
    conn.execute(
        """
        INSERT INTO warehouse.leads (external_id, first_name, last_name, email, company, source, submitted_at, synced_at)
        VALUES (%(external_id)s, %(first_name)s, %(last_name)s, %(email)s, %(company)s, %(source)s, %(submitted_at)s, %(synced_at)s)
        ON CONFLICT (external_id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            email = EXCLUDED.email,
            company = EXCLUDED.company,
            synced_at = EXCLUDED.synced_at
        """,
        record,
    )


def log_event(conn: Connection, external_id: str, status: str, detail: str = "") -> None:
    conn.execute(
        """
        INSERT INTO warehouse.integration_events (external_id, status, detail)
        VALUES (%(external_id)s, %(status)s, %(detail)s)
        """,
        {"external_id": external_id, "status": status, "detail": detail},
    )
