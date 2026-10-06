"""Publishes accepted leads to RabbitMQ with publisher confirms."""

import json

import pika

from src.common.broker import declare_topology, get_connection
from src.common.config import get_settings


def publish_lead(payload: dict) -> None:
    settings = get_settings()
    connection = get_connection()
    try:
        channel = connection.channel()
        declare_topology(channel)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange=settings.exchange_name,
            routing_key=settings.routing_key,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
            mandatory=True,
        )
    finally:
        connection.close()


def check_broker() -> bool:
    try:
        connection = get_connection()
        connection.close()
        return True
    except pika.exceptions.AMQPError:
        return False
