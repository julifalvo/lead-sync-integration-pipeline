-- Schema bootstrap for the lead-sync integration pipeline.
-- crm.* mocks the CRM (HubSpot/Salesforce-like); warehouse.* is the analytics-facing layer.

CREATE SCHEMA IF NOT EXISTS crm;
CREATE SCHEMA IF NOT EXISTS warehouse;

CREATE TABLE IF NOT EXISTS crm.leads (
    id          BIGSERIAL PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL,
    company     TEXT NOT NULL DEFAULT 'Unknown',
    source      TEXT NOT NULL DEFAULT 'webform',
    submitted_at TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bronze layer: every message the worker ever received, verbatim, before any
-- transformation or CRM call. This is what lets the dbt mart layer compute
-- correct funnel/dead-letter-rate numbers *by source* even for leads that
-- never made it into crm.leads/warehouse.leads because the CRM kept failing.
CREATE TABLE IF NOT EXISTS warehouse.raw_lead_events (
    id          BIGSERIAL PRIMARY KEY,
    external_id TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'webform',
    payload     JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warehouse.leads (
    id          BIGSERIAL PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL,
    company     TEXT NOT NULL DEFAULT 'Unknown',
    source      TEXT NOT NULL DEFAULT 'webform',
    submitted_at TIMESTAMPTZ NOT NULL,
    synced_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warehouse.integration_events (
    id          BIGSERIAL PRIMARY KEY,
    external_id TEXT NOT NULL,
    status      TEXT NOT NULL, -- success | error
    detail      TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_warehouse_leads_submitted_at ON warehouse.leads (submitted_at);
CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON warehouse.integration_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_status ON warehouse.integration_events (status);
CREATE INDEX IF NOT EXISTS idx_raw_lead_events_external_id ON warehouse.raw_lead_events (external_id);
