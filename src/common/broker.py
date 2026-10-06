"""RabbitMQ topology shared by the API (publisher) and the worker (consumer).

Topology:
    leads.topic (topic exchange)
          |  routing_key="lead.created"
          v
    leads.queue (durable, x-dead-letter-exchange=leads.dlx)
          |  nack(requeue=False) after retries are exhausted
          v
    leads.dlx (fanout exchange) -> leads.dlq (durable)

This is the standard enterprise-integration pattern for "retry, then quarantine
instead of silently dropping": the worker acks on success, and nacks without
requeue when the CRM call keeps failing after tenacity's retries, which
RabbitMQ automatically routes to the dead-letter queue via x-dead-letter-exchange.
"""

import pika

from src.common.config import get_settings


def declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    settings = get_settings()

    channel.exchange_declare(exchange=settings.exchange_name, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=settings.dlx_name, exchange_type="fanout", durable=True)

    channel.queue_declare(queue=settings.dlq_name, durable=True)
    channel.queue_bind(queue=settings.dlq_name, exchange=settings.dlx_name)

    channel.queue_declare(
        queue=settings.queue_name,
        durable=True,
        arguments={"x-dead-letter-exchange": settings.dlx_name},
    )
    channel.queue_bind(
        queue=settings.queue_name, exchange=settings.exchange_name, routing_key=settings.routing_key
    )


def get_connection() -> pika.BlockingConnection:
    settings = get_settings()
    return pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
