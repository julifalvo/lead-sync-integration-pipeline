# Lead Sync Integration Pipeline

**An end-to-end integration pipeline that syncs web-form leads into a CRM and a
data warehouse in near real time — without duplicating a single record, even
under retries and replayed webhooks.**

Sales and marketing teams lose trust in their CRM when the same lead shows up
twice, or when a flaky integration silently drops a submission. This project
is a self-contained, runnable demo of the integration patterns (webhook
ingestion, async processing, retries with backoff, idempotent upserts,
structured observability) that solve exactly that problem.

![Dashboard demo](./docs/assets/dashboard.gif)

## Business scenario

```
Web form (Typeform-like) --webhook--> Integration API --queue--> Worker --> CRM (mock)
                                                                      \--> Data Warehouse --> Dashboard
```

- **Source**: a simulated web-form submission (`src/generator/generate_leads.py`
  posts realistic fake leads, generated with Faker, to the ingestion API — the
  same shape a real Typeform/Webflow webhook would send).
- **Integration layer**: a FastAPI service validates and authenticates each
  submission, then hands it to a Redis queue so the form never waits on a slow
  downstream system.
- **Processing**: a worker consumes the queue, transforms the payload, and
  upserts it into a mock CRM table and a warehouse table — with retries and
  exponential backoff around a deliberately flaky "CRM API" call.
- **Destination**: Postgres, split into a `crm` schema (mock HubSpot/
  Salesforce) and a `warehouse` schema (analytics-ready leads + an audit log
  of every sync event).
- **Consumption**: a Streamlit dashboard shows leads synced, trends by day and
  source, and recent events/errors.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the reasoning behind every one of
these choices and the trade-offs.

## Architecture

```mermaid
flowchart LR
    G[Lead generator\n(Faker, simulates web form)] -->|POST /webhook/leads\nX-API-Key| A[Integration API\nFastAPI]
    A -->|RPUSH| Q[(Redis queue)]
    Q -->|BLPOP| W[Worker\ntransform + retry/backoff]
    W -->|upsert| CRM[(Postgres: crm.leads)]
    W -->|upsert| WH[(Postgres: warehouse.leads)]
    W -->|audit log| EV[(Postgres: warehouse.integration_events)]
    S[Scheduler\nheartbeat + reconciliation] -.-> A
    S -.-> CRM
    S -.-> WH
    WH --> D[Streamlit dashboard]
    EV --> D
```

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | shared across all services, easy to review |
| API | FastAPI | async, typed, auto docs at `/docs` |
| Queue | Redis (list) | decouples ingestion from processing, zero extra infra |
| Database | Postgres (crm + warehouse schemas) | one free, local engine instead of two |
| Orchestration | APScheduler (custom, documented) | pipeline is streaming, not a batch DAG — see ARCHITECTURE.md |
| Dashboard | Streamlit | fastest way to a real, interactive dashboard |
| Retries | tenacity (exponential backoff) | demonstrates resilience to a flaky CRM |
| Containerization | Docker + docker-compose | `docker-compose up` and everything runs |
| CI | GitHub Actions | ruff + black + pytest + docker build on every push |

## Reliability features

- **Idempotency**: `UNIQUE (external_id)` + upsert on both the CRM and
  warehouse tables. Replaying a webhook or retrying a failed write never
  creates a duplicate.
- **Retries with backoff**: the CRM write is wrapped in `tenacity` with
  exponential backoff (capped at 5 attempts); a simulated failure rate
  (`CRM_FAILURE_RATE`) makes this observable, not theoretical.
- **Structured logs**: every service logs JSON (`{"ts", "level", "service",
  "message", ...}`), ready to ship to an observability stack (Datadog, ELK,
  CloudWatch).
- **Auth**: the ingestion webhook requires an `X-API-Key` header.
- **Audit trail**: every processing outcome (success, duplicate replay,
  error) is written to `warehouse.integration_events`, which backs the
  dashboard's "recent events/errors" panels.

## Running it locally

Requirements: Docker and Docker Compose. Nothing else.

```bash
git clone <this-repo-url> lead-sync-integration-pipeline
cd lead-sync-integration-pipeline
cp .env.example .env
docker-compose up --build
```

Then, once the stack is up:

```bash
# generate ~300 fake leads, replaying ~10% of them to prove idempotency
pip install -r requirements.txt   # or just: pip install requests faker
python -m src.generator.generate_leads --count 300 --duplicate-rate 0.1
```

- **Dashboard**: http://localhost:8501
- **API docs (Swagger)**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

Manual webhook call:

```bash
curl -X POST http://localhost:8000/webhook/leads \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-api-key" \
  -d '{"external_id":"demo-1","full_name":"Ada Lovelace","email":"ada@example.com","company":"Analytical Engines Inc","source":"webform"}'
```

Replay the same `external_id` and check the dashboard's "Duplicate replays
blocked" metric and the `warehouse.integration_events` table — no duplicate
row is created.

## Project structure

```
integration1/
├── src/
│   ├── api/            # FastAPI ingestion webhook (auth, health, enqueue)
│   ├── worker/          # queue consumer: transform, retry/backoff, CRM + warehouse upsert
│   ├── generator/       # fake lead generator (simulates the web form)
│   └── common/          # shared config, structured logging, db, pydantic models
├── orchestration/       # APScheduler heartbeat + reconciliation job
├── dashboard/           # Streamlit app
├── db/init.sql          # Postgres schema (crm + warehouse)
├── tests/               # pytest: transform logic + API endpoint behavior
├── docs/                # screenshots / demo GIF
├── docker-compose.yml
├── .env.example
├── ARCHITECTURE.md      # design decisions and trade-offs
└── .github/workflows/ci.yml
```

## Tests and CI

```bash
pip install -r requirements-dev.txt
ruff check .
black --check .
pytest -v
```

GitHub Actions runs lint, format-check, tests, and a Docker build for every
service on every push (`.github/workflows/ci.yml`).

## What's next / how this would scale

- Swap Redis for Kafka/RabbitMQ to get replay and multiple consumer groups.
- Swap the `warehouse` schema for BigQuery/Snowflake (only `warehouse.py` and
  the dashboard's connection would change).
- Add a dead-letter queue for exhausted retries instead of only logging them.
- Add OpenTelemetry tracing across API → queue → worker.
- Replace the API key with OAuth2 client credentials + per-client rate
  limiting.

## License

MIT — see [LICENSE](./LICENSE).
