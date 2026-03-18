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
