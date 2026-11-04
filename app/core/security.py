import hmac

from fastapi import Header, HTTPException, status

from app.config import settings


def require_admin(x_api_key: str | None = Header(default=None)) -> None:
    """Guard for admin-only endpoints (ingestion, raw query logs, cache controls).

    With no ADMIN_API_KEY configured, access is open in development and
    refused in production so a missing secret can never expose these routes.
    """
    expected = settings.ADMIN_API_KEY
    if not expected:
        if settings.IS_PRODUCTION:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Admin API is not configured.")
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key.")
