"""Lightweight, optional API key authentication.

Behavior:
- AUTH_ENABLED=false: no authentication checks are enforced.
- AUTH_ENABLED=true: a valid API key is required via X-API-Key header
  or api_key query parameter.

Keys are configured via API_KEYS (comma-separated). If auth is enabled and no
keys are configured, a random runtime key is generated and logged at startup.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Header, HTTPException, Query, status

from metricstore.config import settings

_RUNTIME_API_KEYS: set[str] | None = None


def _parse_api_keys(raw: str) -> set[str]:
    return {k.strip() for k in raw.split(",") if k.strip()}


def initialize_auth_runtime() -> None:
    """Initialize runtime API keys (idempotent)."""
    global _RUNTIME_API_KEYS

    if _RUNTIME_API_KEYS is not None:
        return

    if not settings.auth_enabled:
        _RUNTIME_API_KEYS = set()
        return

    configured = _parse_api_keys(settings.api_keys)
    if configured:
        _RUNTIME_API_KEYS = configured
        logging.getLogger("metricstore.auth").info(
            "API key auth enabled with %d configured key(s).", len(configured)
        )
        return

    generated = secrets.token_urlsafe(32)
    _RUNTIME_API_KEYS = {generated}
    logging.getLogger("metricstore.auth").warning(
        "AUTH_ENABLED=true but API_KEYS is empty. Generated runtime API key: %s",
        generated,
    )


def get_active_api_keys() -> set[str]:
    """Return active API keys (empty set when auth is disabled)."""
    if _RUNTIME_API_KEYS is None:
        initialize_auth_runtime()
    return _RUNTIME_API_KEYS or set()


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = Query(default=None),
) -> None:
    """Dependency that enforces API key auth only when enabled."""
    if not settings.auth_enabled:
        return

    provided = x_api_key or api_key
    valid = get_active_api_keys()

    if not provided or provided not in valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
