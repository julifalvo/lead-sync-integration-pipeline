import os

os.environ.setdefault("WEBHOOK_SIGNING_SECRET", "test-signing-secret")
os.environ.setdefault("POSTGRES_DSN", "postgresql://integration:integration@localhost:5432/integration_db")
os.environ.setdefault("RABBITMQ_URL", "amqp://integration:integration@localhost:5672/%2F")
