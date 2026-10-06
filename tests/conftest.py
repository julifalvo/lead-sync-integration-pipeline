import os

os.environ.setdefault("INTEGRATION_API_KEY", "test-api-key")
os.environ.setdefault("POSTGRES_DSN", "postgresql://integration:integration@localhost:5432/integration_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
