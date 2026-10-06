"""Streamlit dashboard: synced leads, trend, and recent integration events."""

import pandas as pd
import psycopg
import streamlit as st

from src.common.config import get_settings

st.set_page_config(page_title="Lead Sync Pipeline", page_icon="📊", layout="wide")


@st.cache_resource
def get_connection():
    return psycopg.connect(get_settings().postgres_dsn, autocommit=True)


def run_query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql(sql, conn)


st.title("📊 Lead Sync Integration Pipeline")
st.caption("Webform → Integration API → Redis queue → Worker → CRM (mock) + Warehouse → this dashboard")

col1, col2, col3, col4 = st.columns(4)

total_leads = run_query("SELECT count(*) AS n FROM warehouse.leads")["n"].iloc[0]
total_events = run_query("SELECT count(*) AS n FROM warehouse.integration_events")["n"].iloc[0]
error_events = run_query("SELECT count(*) AS n FROM warehouse.integration_events WHERE status = 'error'")[
    "n"
].iloc[0]
duplicate_replays = run_query(
    "SELECT count(*) AS n FROM warehouse.integration_events WHERE detail LIKE '%%duplicate replay%%'"
)["n"].iloc[0]

col1.metric("Leads synced", int(total_leads))
col2.metric("Events processed", int(total_events))
col3.metric("Errors (recovered via retry/log)", int(error_events))
col4.metric("Duplicate replays blocked", int(duplicate_replays))

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
    st.subheader("Recent errors")
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
