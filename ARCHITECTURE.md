# Architecture decisions

## Why a queue (Redis) instead of a direct call from the API to the CRM/warehouse?

The webhook endpoint must respond fast and never fail just because a
downstream system is slow or flaky. Decoupling ingestion from processing with
a queue means:
- The form/CRM-of-record integration can absorb traffic spikes without
  dropping submissions.
- The flaky-CRM simulation (see `CRM_FAILURE_RATE`) and its retries happen in
  the worker, off the request path.

Redis is used instead of Kafka/RabbitMQ because the volume and durability
needs of a portfolio-scale pipeline don't justify the operational cost of a
broker; the trade-off (no replay, no consumer groups, no partitioning) is
documented here rather than hidden. A production version handling multiple
consumers or needing replay would move to Kafka or RabbitMQ with minimal
changes to `src/api/queue.py` and `src/worker/main.py`.

## Why Postgres for both the CRM mock and the warehouse?

Running one engine keeps `docker-compose up` single-command and free, matching
the workspace rule of "local and free, cloud documented as extension." The
two roles are kept in **separate schemas** (`crm.*`, `warehouse.*`) rather
than separate databases to mirror how CRM-sourced data lands in a warehouse in
a real stack (e.g. Fivetran/Airbyte syncing Salesforce into Snowflake/BigQuery
schemas), while staying runnable without cloud credentials. Swapping
`warehouse.*` for BigQuery/Snowflake only touches `src/worker/warehouse.py`
and `dashboard/app.py`.

## Why not Airflow/Prefect?

The pipeline is a single always-on streaming hop (webhook → queue → worker),
not a multi-step batch DAG. A full orchestrator would add operational weight
without a corresponding DAG to orchestrate. Instead, `orchestration/scheduler.py`
runs two periodic jobs with APScheduler:
- a heartbeat against `/health` (liveness signal an SRE dashboard would use),
- a reconciliation job that diffs `crm.leads` against `warehouse.leads` to
  catch any lead that made it into the CRM mock but never reached the
  warehouse — the kind of nightly batch check Airflow is usually reached for.

If the pipeline grew additional batch stages (e.g. daily CRM exports, dbt
models, multi-source joins), this scheduler would be replaced by Airflow/
Prefect DAGs; the job functions are already isolated and side-effect-free
enough to port directly into tasks.

## How idempotency is guaranteed

Every lead carries an `external_id` (the form submission ID). Both
`crm.leads` and `warehouse.leads` enforce `UNIQUE (external_id)`, and every
write is an `INSERT ... ON CONFLICT DO UPDATE` upsert. Replaying the same
message — because the webhook was called twice, or the worker retried after a
transient CRM failure — updates the existing row instead of creating a
duplicate. The generator script (`--duplicate-rate`) deliberately replays
some IDs so this is observable end-to-end, not just asserted.

## How retries/backoff work

`src/worker/main.py` wraps the CRM upsert with `tenacity`: exponential backoff
(0.5s → up to 8s), capped at 5 attempts, retrying only on the simulated
`CrmUnavailableError`. Every outcome — success, retried-success, or
exhausted-retries failure — is written to `warehouse.integration_events`,
which is what the dashboard's "recent events/errors" panels read from.

## What would change for a real production deployment

- Replace Redis with Kafka/RabbitMQ for durability, replay, and multiple
  consumer groups.
- Replace the Postgres warehouse schema with a real warehouse (BigQuery/
  Snowflake) and the CRM mock with the real HubSpot/Salesforce API + OAuth.
- Add a dead-letter queue instead of only logging exhausted retries.
- Add distributed tracing (OpenTelemetry) across API → queue → worker.
- Move the API key to a secrets manager and add per-client rate limiting.
