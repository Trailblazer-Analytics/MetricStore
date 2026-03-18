"""Tests for the metrics API routes — service layer is mocked."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from metricstore.main import app

NOW = datetime.now(timezone.utc)
METRIC_ID = uuid.uuid4()

# ── Shared fake ORM objects ───────────────────────────────────────────────────

def _fake_metric(**overrides):
    m = MagicMock()
    m.id = METRIC_ID
    m.name = "monthly_revenue"
    m.display_name = None
    m.description = "Total revenue per month"
    m.formula = None
    m.sql_expression = None
    m.metric_type = "simple"
    m.time_grains = ["day", "week", "month"]
    m.default_time_grain = "day"
    m.dimensions = []
    m.filters = []
    m.owner = "data-team"
    m.owner_email = None
    m.source_platform = None
    m.source_ref = None
    m.tags = ["finance", "revenue"]
    m.meta = {}
    m.status = "active"
    m.deprecated_reason = None
    m.is_public = True
    m.created_at = NOW
    m.updated_at = NOW
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def _fake_version(version_number: int = 1):
    v = MagicMock()
    v.id = uuid.uuid4()
    v.metric_id = METRIC_ID
    v.version_number = version_number
    v.snapshot = {"name": "monthly_revenue"}
    v.change_summary = "Initial version"
    v.changed_by = None
    v.created_at = NOW
    return v


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_svc():
    svc = AsyncMock()
    svc.create_metric.return_value = _fake_metric()
    svc.get_metric.return_value = _fake_metric()
    svc.get_metric_by_name.return_value = _fake_metric()
    svc.list_metrics.return_value = ([_fake_metric()], 1)
    svc.update_metric.return_value = _fake_metric(description="Updated")
    svc.delete_metric.return_value = None
    svc.get_versions.return_value = [_fake_version(2), _fake_version(1)]
    svc.get_version.return_value = _fake_version(1)
    return svc


@pytest.fixture
async def client(mock_svc):
    from metricstore.dependencies import get_metric_service

    app.dependency_overrides[get_metric_service] = lambda: mock_svc
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ── POST /metrics ─────────────────────────────────────────────────────────────

async def test_create_metric_returns_201(client, mock_svc):
    r = await client.post(
        "/api/v1/metrics",
        json={"name": "monthly_revenue", "tags": ["finance"]},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "monthly_revenue"
    assert body["status"] == "active"
    mock_svc.create_metric.assert_called_once()


async def test_create_metric_invalid_name_returns_422(client):
    r = await client.post("/api/v1/metrics", json={"name": "BadName"})
    assert r.status_code == 422


async def test_create_metric_conflict_returns_409(client, mock_svc):
    mock_svc.create_metric.side_effect = HTTPException(status_code=409, detail="exists")
    r = await client.post("/api/v1/metrics", json={"name": "monthly_revenue"})
    assert r.status_code == 409


# ── GET /metrics ──────────────────────────────────────────────────────────────

async def test_list_metrics(client, mock_svc):
    r = await client.get("/api/v1/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["pages"] == 1
    assert len(body["items"]) == 1


async def test_list_metrics_with_filters(client, mock_svc):
    r = await client.get("/api/v1/metrics?search=revenue&tags=finance,revenue&status=active")
    assert r.status_code == 200
    _, kwargs = mock_svc.list_metrics.call_args
    # tags parsed from comma-separated string
    assert kwargs.get("tags") == ["finance", "revenue"]
    assert kwargs.get("search") == "revenue"
    assert kwargs.get("status") == "active"


async def test_list_metrics_page_size_max(client):
    r = await client.get("/api/v1/metrics?page_size=200")
    assert r.status_code == 422  # page_size > 100 should fail


# ── GET /metrics/{id_or_name} ─────────────────────────────────────────────────

async def test_get_metric_by_uuid(client, mock_svc):
    r = await client.get(f"/api/v1/metrics/{METRIC_ID}")
    assert r.status_code == 200
    mock_svc.get_metric.assert_called_once_with(METRIC_ID)


async def test_get_metric_by_name(client, mock_svc):
    r = await client.get("/api/v1/metrics/monthly_revenue")
    assert r.status_code == 200
    mock_svc.get_metric_by_name.assert_called_once_with("monthly_revenue")


async def test_get_metric_not_found_returns_404(client, mock_svc):
    mock_svc.get_metric.side_effect = HTTPException(status_code=404, detail="not found")
    r = await client.get(f"/api/v1/metrics/{METRIC_ID}")
    assert r.status_code == 404


# ── PUT /metrics/{metric_id} ──────────────────────────────────────────────────

async def test_update_metric(client, mock_svc):
    r = await client.put(
        f"/api/v1/metrics/{METRIC_ID}",
        json={"description": "Updated"},
    )
    assert r.status_code == 200
    mock_svc.update_metric.assert_called_once()


async def test_update_metric_invalid_uuid_returns_422(client):
    r = await client.put("/api/v1/metrics/not-a-uuid", json={"description": "x"})
    assert r.status_code == 422


# ── DELETE /metrics/{metric_id} ───────────────────────────────────────────────

async def test_delete_metric_returns_204(client, mock_svc):
    r = await client.delete(f"/api/v1/metrics/{METRIC_ID}")
    assert r.status_code == 204
    mock_svc.delete_metric.assert_called_once_with(METRIC_ID)


# ── Versions ──────────────────────────────────────────────────────────────────

async def test_list_versions(client, mock_svc):
    r = await client.get(f"/api/v1/metrics/{METRIC_ID}/versions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["items"][0]["version_number"] == 2  # newest first


async def test_get_version(client, mock_svc):
    r = await client.get(f"/api/v1/metrics/{METRIC_ID}/versions/1")
    assert r.status_code == 200
    assert r.json()["version_number"] == 1
    mock_svc.get_version.assert_called_once_with(METRIC_ID, 1)


# ── Export ────────────────────────────────────────────────────────────────────

async def test_export_json(client, mock_svc):
    r = await client.post("/api/v1/metrics/export?format=json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert "metrics" in body
    assert len(body["metrics"]) == 1


async def test_export_yaml(client, mock_svc):
    r = await client.post("/api/v1/metrics/export?format=yaml")
    assert r.status_code == 200
    assert "yaml" in r.headers["content-type"]
    assert "monthly_revenue" in r.text


async def test_export_invalid_format(client):
    r = await client.post("/api/v1/metrics/export?format=csv")
    assert r.status_code == 422


# ── Import ────────────────────────────────────────────────────────────────────

async def test_import_metricstore_json(client, mock_svc):
    payload = json_bytes = (
        b'{"metrics": [{"name": "test_metric", "metric_type": "simple"}]}'
    )
    r = await client.post(
        "/api/v1/metrics/import?format=metricstore",
        files={"file": ("metrics.json", payload, "application/json")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 1
    assert body["skipped"] == 0
    assert body["errors"] == []


async def test_import_unsupported_format_returns_501(client):
    r = await client.post(
        "/api/v1/metrics/import?format=dbt",
        files={"file": ("metrics.yml", b"", "text/yaml")},
    )
    assert r.status_code == 501


# ── Health ────────────────────────────────────────────────────────────────────

async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
