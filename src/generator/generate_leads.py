"""Simulates the web-form source: posts realistic fake leads to the API.

Usage:
    python -m src.generator.generate_leads --count 500 --duplicate-rate 0.1

The --duplicate-rate flag deliberately replays some external_ids so a reviewer
can see the idempotency guarantee hold (no duplicate rows, a logged
"updated (duplicate replay)" event) instead of just taking the README's word.
"""

import argparse
import os
import random
import time
import uuid
from datetime import UTC, datetime, timedelta

import requests
from faker import Faker

fake = Faker()

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("INTEGRATION_API_KEY", "dev-local-api-key")

SOURCES = ["webform", "landing_page", "partner_referral", "ad_campaign"]


def build_lead(external_id: str, spread_days: int = 0) -> dict:
    lead = {
        "external_id": external_id,
        "full_name": fake.name(),
        "email": fake.unique.email(),
        "company": fake.company(),
        "source": random.choice(SOURCES),
    }
    if spread_days > 0:
        offset = timedelta(days=random.randint(0, spread_days), hours=random.randint(0, 23))
        lead["submitted_at"] = (datetime.now(UTC) - offset).isoformat()
    return lead


def send(lead: dict) -> None:
    try:
        resp = requests.post(
            f"{API_URL}/webhook/leads",
            json=lead,
            headers={"X-API-Key": API_KEY},
            timeout=5,
        )
        print(f"[{resp.status_code}] {lead['external_id']} {lead['email']}")
    except requests.RequestException as exc:
        print(f"[ERROR] {lead['external_id']}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate lead-form submissions.")
    parser.add_argument("--count", type=int, default=300, help="number of leads to generate")
    parser.add_argument(
        "--duplicate-rate", type=float, default=0.1, help="fraction of leads replayed to test idempotency"
    )
    parser.add_argument("--delay", type=float, default=0.02, help="seconds between submissions")
    parser.add_argument(
        "--spread-days",
        type=int,
        default=0,
        help="backdate submitted_at randomly over this many past days (demo/dashboard purposes)",
    )
    args = parser.parse_args()

    sent_ids: list[str] = []
    for _ in range(args.count):
        if sent_ids and random.random() < args.duplicate_rate:
            external_id = random.choice(sent_ids)
            lead = build_lead(external_id, args.spread_days)
            lead["external_id"] = external_id
        else:
            external_id = str(uuid.uuid4())
            lead = build_lead(external_id, args.spread_days)
            sent_ids.append(external_id)

        send(lead)
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
