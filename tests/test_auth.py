"""Auth behavior tests for optional API-key security."""

from __future__ import annotations

from fastapi.testclient import TestClient

import metricstore.auth as auth_mod
from metricstore.config import settings
from metricstore.main import create_app


def _mcp_initialize_payload() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "auth-tests", "version": "0.1.0"},
        },
    }


def _mcp_headers() -> dict[str, str]:
    return {"accept": "application/json, text/event-stream"}


def _reset_runtime_keys() -> None:
    auth_mod._RUNTIME_API_KEYS = None


def test_no_auth_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "api_keys", "")
    _reset_runtime_keys()

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        # 422 proves route reached without auth barrier.
        assert client.get("/api/v1/metrics?page_size=101").status_code == 422


def test_auth_required_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "test-key")
    _reset_runtime_keys()

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/metrics").status_code == 401
        assert (
            client.post(
                "/mcp", json=_mcp_initialize_payload(), headers=_mcp_headers()
            ).status_code
            == 401
        )


def test_auth_passes_with_valid_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "test-key")
    _reset_runtime_keys()

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/metrics?page_size=101", headers={"X-API-Key": "test-key"}
        )
        assert response.status_code == 422


def test_auth_query_param(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "test-key")
    _reset_runtime_keys()

    app = create_app()
    with TestClient(app) as client:
        # REST via query param
        rest = client.get("/api/v1/metrics?page_size=101&api_key=test-key")
        assert rest.status_code == 422

        # MCP via query param
        mcp = client.post(
            "/mcp?api_key=test-key",
            json=_mcp_initialize_payload(),
            headers=_mcp_headers(),
        )
        assert mcp.status_code == 200
