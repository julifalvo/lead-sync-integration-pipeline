"""Centralized settings loaded from environment variables."""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    postgres_dsn: str
    rabbitmq_url: str
    rabbitmq_management_url: str
    rabbitmq_user: str
    rabbitmq_password: str
    exchange_name: str
    queue_name: str
    dlq_name: str
    dlx_name: str
    routing_key: str
    webhook_signing_secret: str
    crm_failure_rate: float
    worker_metrics_port: int
    log_level: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        postgres_dsn=os.getenv(
            "POSTGRES_DSN",
            "postgresql://integration:integration@localhost:5432/integration_db",
        ),
        rabbitmq_url=os.getenv("RABBITMQ_URL", "amqp://integration:integration@localhost:5672/%2F"),
        rabbitmq_management_url=os.getenv("RABBITMQ_MANAGEMENT_URL", "http://localhost:15672"),
        rabbitmq_user=os.getenv("RABBITMQ_USER", "integration"),
        rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "integration"),
        exchange_name=os.getenv("EXCHANGE_NAME", "leads.topic"),
        queue_name=os.getenv("QUEUE_NAME", "leads.queue"),
        dlq_name=os.getenv("DLQ_NAME", "leads.dlq"),
        dlx_name=os.getenv("DLX_NAME", "leads.dlx"),
        routing_key=os.getenv("ROUTING_KEY", "lead.created"),
        webhook_signing_secret=os.getenv("WEBHOOK_SIGNING_SECRET", "dev-local-signing-secret"),
        crm_failure_rate=float(os.getenv("CRM_FAILURE_RATE", "0.15")),
        worker_metrics_port=int(os.getenv("WORKER_METRICS_PORT", "9100")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
