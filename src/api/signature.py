"""HMAC-SHA256 webhook signature verification (the pattern Stripe/HubSpot/Shopify
webhooks use) instead of a bare shared-secret header.

The signature is computed over the *raw* request body, so a tampered payload
or a replayed body under a different route fails verification even if an
attacker somehow learned the secret's hash. Comparison uses `hmac.compare_digest`
to avoid leaking the secret through a timing side-channel.
"""

import hashlib
import hmac

from fastapi import HTTPException, Request, status

from src.common.config import get_settings
from src.common.metrics import webhook_rejections_total

SIGNATURE_HEADER = "x-signature-256"


def _expected_signature(secret: bytes, body: bytes) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


async def verify_signature(request: Request) -> None:
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER, "")
    expected = _expected_signature(settings.webhook_signing_secret.encode(), body)

    if not signature or not hmac.compare_digest(expected, signature):
        webhook_rejections_total.labels(reason="invalid_signature").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid or missing {SIGNATURE_HEADER} signature",
        )
