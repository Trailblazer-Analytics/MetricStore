"""Integration tests for collections REST API routes."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_collection(test_client) -> None:
    payload = {"name": "finance_metrics", "description": "Finance KPIs"}
    r = await test_client.post("/api/v1/collections", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "finance_metrics"
    assert body["description"] == "Finance KPIs"
    assert body["metric_count"] == 0
    assert "id" in body


@pytest.mark.asyncio
async def test_create_collection_duplicate_name(test_client) -> None:
    payload = {"name": "dupe_collection"}
    await test_client.post("/api/v1/collections", json=payload)
    r = await test_client.post("/api/v1/collections", json=payload)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_list_collections(test_client) -> None:
    for name in ("alpha", "beta", "gamma"):
        await test_client.post("/api/v1/collections", json={"name": name})
    r = await test_client.get("/api/v1/collections")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "alpha" in names
    assert "beta" in names
    assert "gamma" in names


@pytest.mark.asyncio
async def test_get_collection_by_id(test_client) -> None:
    created = await test_client.post(
        "/api/v1/collections",
        json={"name": "get_by_id_test", "description": "desc"},
    )
    assert created.status_code == 201
    cid = created.json()["id"]
    r = await test_client.get(f"/api/v1/collections/{cid}")
    assert r.status_code == 200
    assert r.json()["id"] == cid
    assert r.json()["description"] == "desc"


@pytest.mark.asyncio
async def test_get_collection_not_found(test_client) -> None:
    fake_id = "00000000-0000-0000-0000-000000000001"
    r = await test_client.get(f"/api/v1/collections/{fake_id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_add_metric_to_collection(test_client, seeded_db) -> None:
    created = await test_client.post(
        "/api/v1/collections", json={"name": "my_collection"}
    )
    cid = created.json()["id"]
    mid = str(seeded_db["metrics"]["revenue"].id)

    r = await test_client.post(f"/api/v1/collections/{cid}/metrics/{mid}")
    assert r.status_code == 204

    detail = await test_client.get(f"/api/v1/collections/{cid}")
    assert detail.json()["metric_count"] == 1


@pytest.mark.asyncio
async def test_add_metric_to_collection_duplicate(test_client, seeded_db) -> None:
    created = await test_client.post("/api/v1/collections", json={"name": "dup_link"})
    cid = created.json()["id"]
    mid = str(seeded_db["metrics"]["revenue"].id)

    await test_client.post(f"/api/v1/collections/{cid}/metrics/{mid}")
    r = await test_client.post(f"/api/v1/collections/{cid}/metrics/{mid}")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_add_metric_collection_not_found(test_client, seeded_db) -> None:
    fake_id = "00000000-0000-0000-0000-000000000001"
    mid = str(seeded_db["metrics"]["revenue"].id)
    r = await test_client.post(f"/api/v1/collections/{fake_id}/metrics/{mid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_add_metric_metric_not_found(test_client) -> None:
    created = await test_client.post("/api/v1/collections", json={"name": "coll_nf"})
    cid = created.json()["id"]
    fake_mid = "00000000-0000-0000-0000-000000000002"
    r = await test_client.post(f"/api/v1/collections/{cid}/metrics/{fake_mid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_remove_metric_from_collection(test_client, seeded_db) -> None:
    created = await test_client.post(
        "/api/v1/collections", json={"name": "remove_test"}
    )
    cid = created.json()["id"]
    mid = str(seeded_db["metrics"]["revenue"].id)

    await test_client.post(f"/api/v1/collections/{cid}/metrics/{mid}")
    r = await test_client.delete(f"/api/v1/collections/{cid}/metrics/{mid}")
    assert r.status_code == 204

    detail = await test_client.get(f"/api/v1/collections/{cid}")
    assert detail.json()["metric_count"] == 0


@pytest.mark.asyncio
async def test_remove_metric_not_in_collection(test_client, seeded_db) -> None:
    created = await test_client.post("/api/v1/collections", json={"name": "remove_nf"})
    cid = created.json()["id"]
    mid = str(seeded_db["metrics"]["revenue"].id)
    r = await test_client.delete(f"/api/v1/collections/{cid}/metrics/{mid}")
    assert r.status_code == 404
