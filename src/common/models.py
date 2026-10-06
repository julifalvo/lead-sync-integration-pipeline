"""Pydantic schemas shared by the API and the worker."""

from datetime import UTC, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class LeadIn(BaseModel):
    """Payload accepted at the ingestion webhook (simulated Typeform submission)."""

    external_id: str = Field(..., min_length=1, max_length=64)
    full_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    company: str | None = Field(default=None, max_length=120)
    source: str = Field(default="webform", max_length=40)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class LeadAccepted(BaseModel):
    external_id: str
    status: str = "queued"
