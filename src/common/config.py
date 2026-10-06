"""Centralized settings loaded from environment variables."""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    postgres_dsn: str
    redis_url: str
    api_key: str
    queue_name: str
    crm_failure_rate: float
    log_level: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        postgres_dsn=os.getenv(
            "POSTGRES_DSN",
            "postgresql://integration:integration@localhost:5432/integration_db",
        ),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        api_key=os.getenv("INTEGRATION_API_KEY", "dev-local-api-key"),
        queue_name=os.getenv("QUEUE_NAME", "leads_queue"),
        crm_failure_rate=float(os.getenv("CRM_FAILURE_RATE", "0.15")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
