"""Redis-backed queue used to decouple ingestion from processing."""

import json

import redis

from src.common.config import get_settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def enqueue_lead(payload: dict) -> None:
    settings = get_settings()
    get_redis().rpush(settings.queue_name, json.dumps(payload))
