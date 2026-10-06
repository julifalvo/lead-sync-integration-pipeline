"""Pure transformation logic -- kept dependency-free so it's trivial to unit test."""

from datetime import UTC, datetime
from typing import Any


def clean_company(company: str | None) -> str:
    if not company:
        return "Unknown"
    return company.strip().title()


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def to_crm_record(lead: dict[str, Any]) -> dict[str, Any]:
    """Map the raw webhook payload into the shape the CRM mock expects."""
    first_name, last_name = split_name(lead["full_name"])
    return {
        "external_id": lead["external_id"],
        "first_name": first_name,
        "last_name": last_name,
        "email": lead["email"].strip().lower(),
        "company": clean_company(lead.get("company")),
        "source": lead.get("source", "webform"),
        "submitted_at": lead["submitted_at"],
    }


def to_warehouse_record(crm_record: dict[str, Any]) -> dict[str, Any]:
    """Map a CRM record into the warehouse fact shape (adds a sync timestamp)."""
    return {
        **crm_record,
        "synced_at": datetime.now(UTC).isoformat(),
    }
