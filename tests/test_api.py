import hashlib
import hmac
import json
from contextlib import contextmanager

from fastapi.testclient import TestClient

from src.api import main as api_main

client = TestClient(api_main.app)
SIGNING_SECRET = "test-signing-secret"

VALID_LEAD = {
    "external_id": "lead-001",
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "company": "Analytical Engines Inc",
    "source": "webform",
}


def signed_headers(body: bytes) -> dict:
    signature = "sha256=" + hmac.new(SIGNING_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-Signature-256": signature}


def post_lead(lead: dict, headers: dict | None = None):
    body = json.dumps(lead).encode()
    return client.post("/webhook/leads", content=body, headers=headers or signed_headers(body))


def test_webhook_rejects_missing_signature():
    body = json.dumps(VALID_LEAD).encode()
    resp = client.post("/webhook/leads", content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 401


def test_webhook_rejects_wrong_signature():
    resp = post_lead(
        VALID_LEAD, headers={"Content-Type": "application/json", "X-Signature-256": "sha256=deadbeef"}
    )
    assert resp.status_code == 401


def test_webhook_rejects_tampered_body():
    body = json.dumps(VALID_LEAD).encode()
    headers = signed_headers(body)  # signature computed over the *original* body
    tampered = json.dumps({**VALID_LEAD, "email": "attacker@example.com"}).encode()
    resp = client.post("/webhook/leads", content=tampered, headers=headers)
    assert resp.status_code == 401


def test_webhook_rejects_invalid_payload():
    bad_lead = {**VALID_LEAD, "email": "not-an-email"}
    resp = post_lead(bad_lead)
    assert resp.status_code == 422


def test_webhook_accepts_valid_lead(monkeypatch):
    calls = []
    monkeypatch.setattr(api_main, "publish_lead", lambda payload: calls.append(payload))

    resp = post_lead(VALID_LEAD)

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

    monkeypatch.setattr(api_main, "get_conn", broken_conn)
    monkeypatch.setattr(api_main, "check_broker", lambda: False)

    resp = client.get("/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["postgres"] is False
    assert body["rabbitmq"] is False
