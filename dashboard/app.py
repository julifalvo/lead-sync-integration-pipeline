"""Streamlit dashboard: synced leads, trend, queue health, and recent events."""

import pandas as pd
import psycopg
import requests
import streamlit as st

from src.common.config import get_settings

st.set_page_config(page_title="Lead Sync Pipeline", page_icon="📊", layout="wide")

settings = get_settings()


@st.cache_resource
def get_connection():
    return psycopg.connect(settings.postgres_dsn, autocommit=True)


def run_query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql(sql, conn)


def queue_depth(queue_name: str) -> int | None:
    try:
        resp = requests.get(
            f"{settings.rabbitmq_management_url}/api/queues/%2F/{queue_name}",
            auth=(settings.rabbitmq_user, settings.rabbitmq_password),
            timeout=2,
        )
        resp.raise_for_status()
        return resp.json().get("messages", 0)
    except requests.RequestException:
        return None


st.title("📊 Lead Sync Integration Pipeline")
st.caption(
    "Webform → Integration API (HMAC-verified) → RabbitMQ → Worker (retry/backoff + DLQ) "
    "→ CRM (mock) + Warehouse → this dashboard"
)

col1, col2, col3, col4, col5, col6 = st.columns(6)

total_leads = run_query("SELECT count(*) AS n FROM warehouse.leads")["n"].iloc[0]
total_events = run_query("SELECT count(*) AS n FROM warehouse.integration_events")["n"].iloc[0]
error_events = run_query("SELECT count(*) AS n FROM warehouse.integration_events WHERE status = 'error'")[
    "n"
].iloc[0]
duplicate_replays = run_query(
    "SELECT count(*) AS n FROM warehouse.integration_events WHERE detail LIKE '%%duplicate replay%%'"
)["n"].iloc[0]

main_depth = queue_depth(settings.queue_name)
dlq_depth = queue_depth(settings.dlq_name)

col1.metric("Leads synced", int(total_leads))
col2.metric("Events processed", int(total_events))
col3.metric("Dead-lettered (after retries)", int(error_events))
col4.metric("Duplicate replays blocked", int(duplicate_replays))
col5.metric("Queue depth", main_depth if main_depth is not None else "n/a")
col6.metric("DLQ depth", dlq_depth if dlq_depth is not None else "n/a")

if dlq_depth:
    st.warning(
        f"{dlq_depth} message(s) sitting in the dead-letter queue (`{settings.dlq_name}`) -- "
        "the CRM mock kept failing past the retry budget. Inspect them in the RabbitMQ "
        "management UI (http://localhost:15672)."
    )

st.subheader("Leads synced per day")
daily = run_query(
    """
    SELECT date_trunc('day', submitted_at)::date AS day, count(*) AS leads
    FROM warehouse.leads
    GROUP BY 1
    ORDER BY 1
    """
)
if not daily.empty:
    st.bar_chart(daily.set_index("day"))
else:
    st.info("No leads synced yet. Run the generator: `python -m src.generator.generate_leads`.")

st.subheader("Leads by source")
by_source = run_query("SELECT source, count(*) AS leads FROM warehouse.leads GROUP BY 1 ORDER BY 2 DESC")
if not by_source.empty:
    st.bar_chart(by_source.set_index("source"))

left, right = st.columns(2)

with left:
    st.subheader("Recent events")
    events = run_query(
        """
        SELECT occurred_at, external_id, status, detail
        FROM warehouse.integration_events
        ORDER BY occurred_at DESC
        LIMIT 25
        """
    )
    st.dataframe(events, use_container_width=True, hide_index=True)

with right:
    st.subheader("Recent errors / dead-letters")
    errors = run_query(
        """
        SELECT occurred_at, external_id, detail
        FROM warehouse.integration_events
        WHERE status = 'error'
        ORDER BY occurred_at DESC
        LIMIT 25
        """
    )
    if errors.empty:
        st.success("No errors logged.")
    else:
        st.dataframe(errors, use_container_width=True, hide_index=True)
