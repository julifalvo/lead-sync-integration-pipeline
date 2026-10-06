"""API-key authentication for the ingestion endpoints."""

from fastapi import Header, HTTPException, status

from src.common.config import get_settings


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    settings = get_settings()
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
