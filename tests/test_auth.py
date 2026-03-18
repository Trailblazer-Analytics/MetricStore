"""Authentication behavior tests for REST and MCP interfaces."""

from __future__ import annotations

from fastapi.testclient import TestClient

import metricstore.auth as auth_mod
from metricstore.config import settings
from metricstore.main import create_app


def _mcp_init_payload() -> dict:
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


def _reset_auth_runtime() -> None:
    auth_mod._RUNTIME_API_KEYS = None


def test_auth_disabled_allows_requests_without_key(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "api_keys", "")
    _reset_auth_runtime()

    app = create_app()
    with TestClient(app) as client:
        # Health/docs should always be public.
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200

        # REST route is reachable without key (422 is from request validation).
        api_resp = client.get("/api/v1/metrics?page_size=101")
        assert api_resp.status_code == 422

        # MCP also reachable without key when auth is disabled.
        mcp_resp = client.post("/mcp", json=_mcp_init_payload(), headers=_mcp_headers())
        assert mcp_resp.status_code == 200


def test_auth_enabled_requires_valid_key_for_rest_and_mcp(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "test-key")
    _reset_auth_runtime()

    app = create_app()
    with TestClient(app) as client:
        # Public endpoints remain unauthenticated.
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200

        # REST without key is rejected.
        assert client.get("/api/v1/metrics").status_code == 401

        # REST with key works (422 from validation, not auth).
        assert (
            client.get("/api/v1/metrics?page_size=101", headers={"X-API-Key": "test-key"}).status_code
            == 422
        )
        assert client.get("/api/v1/metrics?page_size=101&api_key=test-key").status_code == 422

        # MCP without key is rejected.
        assert (
            client.post("/mcp", json=_mcp_init_payload(), headers=_mcp_headers()).status_code
            == 401
        )

        # MCP with query key is accepted.
        mcp_ok = client.post(
            "/mcp?api_key=test-key", json=_mcp_init_payload(), headers=_mcp_headers()
        )
        assert mcp_ok.status_code == 200


def test_auth_enabled_generates_runtime_key_when_missing(monkeypatch, caplog):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "")
    _reset_auth_runtime()

    app = create_app()
    with TestClient(app) as client:
        keys = auth_mod.get_active_api_keys()
        assert len(keys) == 1
        generated = next(iter(keys))
        assert len(generated) >= 20

        # Generated key should authorize API access.
        resp = client.get("/api/v1/metrics?page_size=101", headers={"X-API-Key": generated})
        assert resp.status_code == 422

    assert "Generated runtime API key" in caplog.text
