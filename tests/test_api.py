from contextlib import contextmanager

from fastapi.testclient import TestClient

from src.api import main as api_main

client = TestClient(api_main.app)
API_KEY = "test-api-key"

VALID_LEAD = {
    "external_id": "lead-001",
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "company": "Analytical Engines Inc",
    "source": "webform",
}


def test_webhook_rejects_missing_api_key():
    resp = client.post("/webhook/leads", json=VALID_LEAD)
    assert resp.status_code == 401


def test_webhook_rejects_wrong_api_key():
    resp = client.post("/webhook/leads", json=VALID_LEAD, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_webhook_rejects_invalid_payload():
    bad_lead = {**VALID_LEAD, "email": "not-an-email"}
    resp = client.post("/webhook/leads", json=bad_lead, headers={"X-API-Key": API_KEY})
    assert resp.status_code == 422


def test_webhook_accepts_valid_lead(monkeypatch):
    calls = []
    monkeypatch.setattr(api_main, "enqueue_lead", lambda payload: calls.append(payload))

    resp = client.post("/webhook/leads", json=VALID_LEAD, headers={"X-API-Key": API_KEY})

    assert resp.status_code == 202
    body = resp.json()
    assert body["external_id"] == "lead-001"
    assert body["status"] == "queued"
    assert len(calls) == 1
    assert calls[0]["external_id"] == "lead-001"


def test_health_reports_degraded_when_dependencies_down(monkeypatch):
    @contextmanager
    def broken_conn():
        raise RuntimeError("no postgres")
        yield  # pragma: no cover

    class BrokenRedis:
        def ping(self):
            raise RuntimeError("no redis")

    monkeypatch.setattr(api_main, "get_conn", broken_conn)
    monkeypatch.setattr(api_main, "get_redis", lambda: BrokenRedis())

    resp = client.get("/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["postgres"] is False
    assert body["redis"] is False
