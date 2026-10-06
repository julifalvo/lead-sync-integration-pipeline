"""Mock CRM: a Postgres table standing in for HubSpot/Salesforce.

Randomly raises to simulate a flaky third-party API, so the retry/backoff
logic in worker.main has something real to exercise.
"""

import random

from psycopg import Connection

from src.common.config import get_settings


class CrmUnavailableError(RuntimeError):
    pass


def upsert_lead(conn: Connection, record: dict) -> bool:
    """Insert or update a lead in the CRM. Returns True if it was a new lead."""
    settings = get_settings()
    if random.random() < settings.crm_failure_rate:
        raise CrmUnavailableError("simulated CRM timeout")

    row = conn.execute(
        """
        INSERT INTO crm.leads (external_id, first_name, last_name, email, company, source, submitted_at)
        VALUES (%(external_id)s, %(first_name)s, %(last_name)s, %(email)s, %(company)s, %(source)s, %(submitted_at)s)
        ON CONFLICT (external_id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            email = EXCLUDED.email,
            company = EXCLUDED.company,
            updated_at = now()
        RETURNING (xmax = 0) AS inserted
        """,
        record,
    ).fetchone()
    return bool(row["inserted"])
