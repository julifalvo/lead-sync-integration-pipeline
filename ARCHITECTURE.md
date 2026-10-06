# Architecture decisions

## Why RabbitMQ instead of a direct call from the API to the CRM/warehouse?

The webhook endpoint must respond fast and never fail just because a
downstream system is slow or flaky. Decoupling ingestion from processing with
a broker means:
- The form/CRM-of-record integration can absorb traffic spikes without
  dropping submissions (the API publishes with **publisher confirms**, so it
  only 202s once RabbitMQ has durably accepted the message).
- The flaky-CRM simulation (see `CRM_FAILURE_RATE`) and its retries happen in
  the worker, off the request path.

RabbitMQ (not a plain Redis list) was chosen because it gives the pipeline the
two things an enterprise integration actually needs and a list-backed queue
can't: a **topology** (`leads.topic` exchange → `leads.queue`, topic-routed so
more event types can be added later without new infra) and **dead-lettering**
(see below) as a first-class broker feature instead of app-level bookkeeping.
See `src/common/broker.py` for the topology declaration. Kafka would be the
next step up if the pipeline needed replay/multiple consumer groups across
services — documented as a future step, not implemented, to keep the stack
runnable with `docker-compose up` and no cluster to operate.

## How dead-lettering works

`leads.queue` is declared with `x-dead-letter-exchange: leads.dlx`. The worker
acks on success and **nacks without requeue** once `tenacity` exhausts its 5
retry attempts against the CRM mock — RabbitMQ then automatically routes that
message to `leads.dlx` → `leads.dlq` instead of retrying forever or dropping
it silently. The dashboard surfaces `leads.dlq`'s depth (via the RabbitMQ
management HTTP API) with a warning banner, and every dead-letter is also
logged to `warehouse.integration_events` so it shows up in the audit trail
even if nobody is watching the queue depth. `orchestration/n8n/lead-ops-alerts.json`
is a (optional, `--profile ops`) low-code n8n workflow that polls that same
depth and would page on-call in a real deployment.

## Why HMAC-signed webhooks instead of a bare API-key header?

A shared-secret header (`X-API-Key: ...`) proves the caller knows a secret,
but says nothing about whether the body in transit is the body that was
signed. `src/api/signature.py` instead verifies an `X-Signature-256:
sha256=<hmac>` header computed over the **raw request body** with a shared
secret — the same pattern Stripe, HubSpot, and Shopify webhooks use. This
catches body tampering, not just missing credentials, and `hmac.compare_digest`
is used instead of `==` to avoid leaking the secret through a timing
side-channel. `src/generator/generate_leads.py` signs every request the same
way a real upstream system would.

## Why Postgres for both the CRM mock and the warehouse?

Running one engine keeps `docker-compose up` single-command and free, matching
the workspace rule of "local and free, cloud documented as extension." The
roles are kept in **separate schemas**:
- `crm.*` — mocks the CRM of record (HubSpot/Salesforce-like).
- `warehouse.raw_lead_events` — **bronze**: every message the worker ever
  received, verbatim, before any transform or CRM call. This exists
  specifically so a lead that gets dead-lettered (and therefore never reaches
  `crm.leads`) can still be attributed to a `source` in analytics — a real
  gap teams hit when they only persist the "happy path" record.
- `warehouse.leads` — **silver**: one row per lead successfully synced,
  idempotently upserted.
- `warehouse.integration_events` — the audit trail of every processing
  outcome (success / error).
- `analytics_marts.*` — **gold**: the dbt mart layer built on top (see below).

This mirrors how CRM-sourced data lands in a warehouse in a real stack (e.g.
Fivetran/Airbyte syncing Salesforce into Snowflake/BigQuery schemas), while
staying runnable without cloud credentials. Swapping `warehouse.*` for
BigQuery/Snowflake only touches `src/worker/warehouse.py` and `dashboard/app.py`.

## The dbt mart layer (optional, `--profile dbt`)

`dbt/` is a small dbt-postgres project: `models/staging/` views the three
warehouse tables above (with not-null/unique/accepted-values tests), and
`models/marts/` builds two gold tables —
`mart_daily_lead_funnel` (received → synced → dead-lettered, by day) and
`mart_source_performance` (the same funnel, by lead source) — specifically to
answer "which source's integration is unreliable" without grepping logs. It's
not part of the default `docker-compose up` because it's a point-in-time
batch job, not a running service: run it with
`docker compose --profile dbt run --rm dbt build`. CI runs it on every push
against real seeded data (see `.github/workflows/ci.yml`), so a broken model
or a failing data test fails the build, not just a local `dbt run`.

## Why not Airflow/Prefect?

The pipeline is a single always-on streaming hop (webhook → queue → worker),
not a multi-step batch DAG. A full orchestrator would add operational weight
without a corresponding DAG to orchestrate. Instead, `orchestration/scheduler.py`
runs two periodic jobs with APScheduler:
- a heartbeat against `/health` (liveness signal an SRE dashboard would use),
- a reconciliation job that diffs `crm.leads` against `warehouse.leads` to
  catch any lead that made it into the CRM mock but never reached the
  warehouse — the kind of nightly batch check Airflow is usually reached for.

If the pipeline grew additional batch stages (nightly CRM exports, more dbt
models, multi-source joins), this scheduler would be replaced by Airflow/
Prefect DAGs; the job functions are already isolated and side-effect-free
enough to port directly into tasks. The dbt mart layer is the first model of
what would become one.

## Why n8n for the ops layer, instead of writing the alerting in Python?

`orchestration/n8n/lead-ops-alerts.json` is a workflow (polls the DLQ depth
every 5 minutes, branches on "is it non-zero") that intentionally sits
**outside** the Python codebase. In real integration teams, the core sync
logic is owned by engineers and lives in code, but day-2 operational flows
(alerting, routing, "when X happens notify #channel") are frequently owned by
ops/support and built in a low-code tool so they can be changed without a
deploy. n8n is one of the most common choices for that layer in 2026. It's
gated behind `docker compose --profile ops up n8n` rather than being part of
the core stack, because it's genuinely optional — the pipeline is fully
correct and observable (Prometheus/Grafana, the dashboard's DLQ banner)
without it.

## Observability: Prometheus + Grafana vs. just the Streamlit dashboard

The Streamlit dashboard answers "what's in the warehouse right now" from
Postgres — it's a business-facing view. `src/common/metrics.py` exposes
counters/histograms (`leads_ingested_total`, `leads_processed_total`,
`leads_dead_lettered_total`, `crm_retry_attempts_total`,
`lead_processing_seconds`) that the API and worker serve on `/metrics`;
Prometheus scrapes both every 10s and Grafana (provisioned automatically —
datasource + the `Lead Sync Integration Pipeline` dashboard both load with no
manual clicking, see `observability/`) answers the operational question: "is
the pipeline healthy *right now*, and what's the trend." That split (business
dashboard vs. operational metrics) mirrors how real teams separate a
product/BI tool from an SRE-facing one instead of overloading a single view.

## How idempotency is guaranteed

Every lead carries an `external_id` (the form submission ID). Both
`crm.leads` and `warehouse.leads` enforce `UNIQUE (external_id)`, and every
write is an `INSERT ... ON CONFLICT DO UPDATE` upsert. Replaying the same
message — because the webhook was called twice, or a message is redelivered
after a worker crash — updates the existing row instead of creating a
duplicate. The generator script (`--duplicate-rate`) deliberately replays
some IDs so this is observable end-to-end, not just asserted.

## How retries/backoff work

`src/worker/main.py` wraps the CRM upsert with `tenacity`: exponential backoff
(0.5s → up to 8s), capped at 5 attempts, retrying only on the simulated
`CrmUnavailableError`. Every outcome — success, retried-success, or
exhausted-retries (dead-lettered) — is written to
`warehouse.integration_events`, which is what the dashboard's "recent
events/errors" panel and the `crm_retry_attempts_total` /
`leads_dead_lettered_total` Prometheus counters are built from.

## What would change for a real production deployment

- Swap RabbitMQ for Kafka if the pipeline grew to need replay or multiple
  independent consumer groups across services.
- Replace the Postgres warehouse schema with a real warehouse (BigQuery/
  Snowflake) and the CRM mock with the real HubSpot/Salesforce API + OAuth.
- Add distributed tracing (OpenTelemetry) across API → queue → worker.
- Add a timestamp + nonce to the webhook signature to defend against replay
  of a captured, validly-signed request (not just tampering).
- Move the signing secret to a secrets manager and add per-client rate
  limiting.
- Promote `orchestration/n8n/lead-ops-alerts.json`'s NoOp nodes to real
  Slack/PagerDuty nodes.
