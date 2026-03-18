"""MCP smoke tests.

Full MCP protocol compliance testing requires dedicated MCP clients; these tests
focus on endpoint existence and tool discovery.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_mcp_endpoint_exists(test_client) -> None:
    response = await test_client.get("/mcp/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["path"] == "/mcp"


@pytest.mark.asyncio
async def test_mcp_tool_list(test_client) -> None:
    headers = {"accept": "application/json, text/event-stream"}
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0.1.0"},
        },
    }
    init = await test_client.post("/mcp", json=init_payload, headers=headers)
    assert init.status_code == 200
    sid = init.headers.get("mcp-session-id")
    assert sid

    tool_list = await test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={**headers, "mcp-session-id": sid},
    )
    assert tool_list.status_code == 200
    names = [t["name"] for t in tool_list.json()["result"]["tools"]]

    for tool in [
        "discover_metrics",
        "get_metric_definition",
        "search_metrics",
        "get_metric_sql",
        "list_collections",
        "get_collection_metrics",
    ]:
        assert tool in names


# ── Custom tool REST endpoints ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_discover_metrics(test_client, seeded_db) -> None:
    r = await test_client.get("/mcp/tools/discover_metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "discover_metrics"
    assert body["count"] >= 8


@pytest.mark.asyncio
async def test_mcp_discover_metrics_with_search(test_client, seeded_db) -> None:
    r = await test_client.get("/mcp/tools/discover_metrics?search=revenue")
    assert r.status_code == 200
    body = r.json()
    assert any(item["name"] == "revenue" for item in body["items"])


@pytest.mark.asyncio
async def test_mcp_discover_metrics_with_filters(test_client, seeded_db) -> None:
    r = await test_client.get(
        "/mcp/tools/discover_metrics?tags=marketing&status=active&metric_type=derived"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert all("marketing" in item["tags"] for item in body["items"])


@pytest.mark.asyncio
async def test_mcp_search_metrics(test_client, seeded_db) -> None:
    r = await test_client.get("/mcp/tools/search_metrics?query=revenue")
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "search_metrics"
    assert body["query"] == "revenue"
    assert any(item["name"] == "revenue" for item in body["items"])


@pytest.mark.asyncio
async def test_mcp_search_metrics_medium_relevance(test_client, seeded_db) -> None:
    r = await test_client.get("/mcp/tools/search_metrics?query=customer")
    assert r.status_code == 200
    body = r.json()
    assert any(item["relevance"] == "medium" for item in body["items"])


@pytest.mark.asyncio
async def test_mcp_get_metric_definition(test_client, seeded_db) -> None:
    r = await test_client.get("/mcp/tools/get_metric_definition?metric_name=revenue")
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "get_metric_definition"
    assert body["metric"]["name"] == "revenue"


@pytest.mark.asyncio
async def test_mcp_get_metric_sql(test_client, seeded_db) -> None:
    r = await test_client.get("/mcp/tools/get_metric_sql?metric_name=revenue")
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "get_metric_sql"
    assert body["metric_name"] == "revenue"


@pytest.mark.asyncio
async def test_mcp_get_metric_sql_with_time_grain_override(
    test_client, seeded_db
) -> None:
    r = await test_client.get(
        "/mcp/tools/get_metric_sql?metric_name=revenue&time_grain=month"
    )
    assert r.status_code == 200
    assert r.json()["time_grain"] == "month"


@pytest.mark.asyncio
async def test_mcp_list_collections_empty(test_client) -> None:
    r = await test_client.get("/mcp/tools/list_collections")
    assert r.status_code == 200
    body = r.json()
    assert body["tool"] == "list_collections"
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_mcp_list_collections_with_counts(test_client, seeded_db) -> None:
    collection = await test_client.post(
        "/api/v1/collections", json={"name": "mcp_collection"}
    )
    collection_id = collection.json()["id"]
    metric_id = seeded_db["metrics"]["revenue"].id

    add_metric = await test_client.post(
        f"/api/v1/collections/{collection_id}/metrics/{metric_id}"
    )
    assert add_metric.status_code == 204

    r = await test_client.get("/mcp/tools/list_collections")
    assert r.status_code == 200
    body = r.json()
    item = next(row for row in body["items"] if row["name"] == "mcp_collection")
    assert item["metric_count"] == 1


@pytest.mark.asyncio
async def test_mcp_get_collection_metrics_not_found(test_client) -> None:
    r = await test_client.get(
        "/mcp/tools/get_collection_metrics?collection_name=nonexistent"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert "not found" in body["context"].lower()


@pytest.mark.asyncio
async def test_mcp_get_collection_metrics_success(test_client, seeded_db) -> None:
    collection = await test_client.post(
        "/api/v1/collections", json={"name": "revenue_metrics"}
    )
    collection_id = collection.json()["id"]
    metric_id = seeded_db["metrics"]["revenue"].id

    add_metric = await test_client.post(
        f"/api/v1/collections/{collection_id}/metrics/{metric_id}"
    )
    assert add_metric.status_code == 204

    r = await test_client.get(
        "/mcp/tools/get_collection_metrics?collection_name=revenue_metrics"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["name"] == "revenue"
