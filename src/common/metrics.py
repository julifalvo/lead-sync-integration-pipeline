"""Prometheus metrics shared across the API and the worker."""

from prometheus_client import Counter, Histogram

leads_ingested_total = Counter(
    "leads_ingested_total", "Leads accepted at the webhook, before queueing", ["source"]
)
webhook_rejections_total = Counter("webhook_rejections_total", "Webhook requests rejected", ["reason"])

leads_processed_total = Counter(
    "leads_processed_total", "Leads successfully synced to CRM + warehouse", ["outcome"]
)
leads_dead_lettered_total = Counter(
    "leads_dead_lettered_total", "Leads that exhausted retries and were routed to the DLQ"
)
crm_retry_attempts_total = Counter(
    "crm_retry_attempts_total", "Attempts made against the (simulated) CRM, including retries"
)
lead_processing_seconds = Histogram(
    "lead_processing_seconds", "Time spent processing one lead message end to end"
)
