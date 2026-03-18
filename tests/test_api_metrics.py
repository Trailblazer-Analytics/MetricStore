"""Integration tests for metrics REST API routes."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_metric(test_client):
    payload = {
        "name": "gross_margin",
        "description": "Gross margin percentage.",
        "metric_type": "derived",
        "formula": "(revenue - cogs) / revenue",
        "tags": ["finance"],
        "owner": "Finance Analytics",
    }
    r = await test_client.post("/api/v1/metrics", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == payload["name"]
    assert body["metric_type"] == payload["metric_type"]
    assert "id" in body


@pytest.mark.asyncio
async def test_create_metric_duplicate_name(test_client, seeded_db):
    payload = {"name": "revenue", "metric_type": "simple"}
    r = await test_client.post("/api/v1/metrics", json=payload)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_get_metric_by_id(test_client, seeded_db):
    revenue = seeded_db["metrics"]["revenue"]
    r = await test_client.get(f"/api/v1/metrics/{revenue.id}")
    assert r.status_code == 200
    body = r.json()
    for key in [
        "id",
        "name",
        "metric_type",
        "time_grains",
        "default_time_grain",
        "dimensions",
        "filters",
        "status",
        "created_at",
        "updated_at",
    ]:
        assert key in body
    assert body["name"] == "revenue"


@pytest.mark.asyncio
async def test_get_metric_by_name(test_client, seeded_db):
    r = await test_client.get("/api/v1/metrics/revenue")
    assert r.status_code == 200
    assert r.json()["name"] == "revenue"


@pytest.mark.asyncio
async def test_list_metrics_pagination(test_client, seeded_db):
    r1 = await test_client.get("/api/v1/metrics?page=1&page_size=3")
    r2 = await test_client.get("/api/v1/metrics?page=2&page_size=3")
    assert r1.status_code == 200
    assert r2.status_code == 200
    b1 = r1.json()
    b2 = r2.json()
    assert b1["page"] == 1
    assert b1["page_size"] == 3
    assert b1["total"] >= 8
    assert len(b1["items"]) == 3
    assert b2["page"] == 2


@pytest.mark.asyncio
async def test_list_metrics_search(test_client, seeded_db):
    r = await test_client.get("/api/v1/metrics?search=churn")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["name"] == "churn_rate" for i in items)


@pytest.mark.asyncio
async def test_list_metrics_filter_tags(test_client, seeded_db):
    r = await test_client.get("/api/v1/metrics?tags=marketing")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    assert all("marketing" in i["tags"] for i in items)


@pytest.mark.asyncio
async def test_list_metrics_filter_status(test_client, seeded_db):
    r = await test_client.get("/api/v1/metrics?status=draft")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    assert all(i["status"] == "draft" for i in items)


@pytest.mark.asyncio
async def test_update_metric(test_client, seeded_db):
    revenue = seeded_db["metrics"]["revenue"]

    before = await test_client.get(f"/api/v1/metrics/{revenue.id}/versions")
    assert before.status_code == 200
    before_count = before.json()["total"]

    payload = {
        "description": "Updated revenue definition for integration test.",
        "status": "active",
    }
    r = await test_client.put(f"/api/v1/metrics/{revenue.id}", json=payload)
    assert r.status_code == 200
    assert r.json()["description"] == payload["description"]

    after = await test_client.get(f"/api/v1/metrics/{revenue.id}/versions")
    assert after.status_code == 200
    assert after.json()["total"] == before_count + 1


@pytest.mark.asyncio
async def test_delete_metric(test_client, seeded_db):
    target = seeded_db["metrics"]["nps_score"]
    r = await test_client.delete(f"/api/v1/metrics/{target.id}")
    assert r.status_code == 204

    gone = await test_client.get(f"/api/v1/metrics/{target.id}")
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_export_json(test_client, seeded_db):
    r = await test_client.post("/api/v1/metrics/export?format=json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "Content-Disposition" in r.headers
    body = r.json()
    assert "metadata" in body
    assert "metrics" in body
    assert body["metadata"]["source"] == "metricstore"


@pytest.mark.asyncio
async def test_export_yaml(test_client, seeded_db):
    r = await test_client.post("/api/v1/metrics/export?format=yaml")
    assert r.status_code == 200
    assert "yaml" in r.headers["content-type"]
    assert "Content-Disposition" in r.headers
    assert r.text.startswith("# Exported from MetricStore")
    assert "metrics:" in r.text


@pytest.mark.asyncio
async def test_metric_versions(test_client, seeded_db):
    metric = seeded_db["metrics"]["mrr"]

    for idx in range(2):
        payload = {"description": f"mrr updated {idx}"}
        r = await test_client.put(f"/api/v1/metrics/{metric.id}", json=payload)
        assert r.status_code == 200

    versions = await test_client.get(f"/api/v1/metrics/{metric.id}/versions")
    assert versions.status_code == 200
    body = versions.json()
    assert body["total"] >= 3
    nums = [v["version_number"] for v in body["items"]]
    assert nums == sorted(nums, reverse=True)


@pytest.mark.asyncio
async def test_get_specific_version(test_client, seeded_db):
    metric = seeded_db["metrics"]["cac"]

    upd = await test_client.put(
        f"/api/v1/metrics/{metric.id}",
        json={"description": "CAC updated for version test"},
    )
    assert upd.status_code == 200

    v1 = await test_client.get(f"/api/v1/metrics/{metric.id}/versions/1")
    assert v1.status_code == 200
    snap = v1.json()["snapshot"]
    assert snap["name"] == "cac"
    assert "description" in snap
