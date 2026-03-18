"""MCP (Model Context Protocol) integration for MetricStore.

This module does two things:
1. Mounts fastapi-mcp at /mcp, auto-exposing REST endpoints as MCP tools.
2. Adds custom AI-optimized wrapper tools under /mcp/tools/*.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi_mcp import FastApiMCP
from fastapi_mcp.types import AuthConfig
from sqlalchemy.ext.asyncio import AsyncSession

from metricstore.auth import require_api_key
from metricstore.dependencies import get_db
from metricstore.services.collection_service import CollectionService
from metricstore.services.metric_service import MetricService


def _create_custom_mcp_router() -> APIRouter:
    router = APIRouter(
        prefix="/mcp",
        tags=["mcp-tools"],
        dependencies=[Depends(require_api_key)],
    )

    @router.get(
        "/health",
        operation_id="mcp_health",
        summary="MCP server health",
        description="Status endpoint for the MCP interface.",
    )
    async def mcp_health() -> dict[str, Any]:
        return {
            "status": "ok",
            "interface": "mcp",
            "transport": "streamable-http",
            "path": "/mcp",
            "custom_tools_path": "/mcp/tools",
        }

    @router.get(
        "/tools/discover_metrics",
        operation_id="discover_metrics",
        summary="Discover available metrics",
        description=(
            "List all available business metrics in the catalog. Returns metric "
            "names, descriptions, types, and owners. Use this first to understand "
            "what metrics are available before querying specific ones. Supports "
            "filtering by tags, status, metric type, and text search."
        ),
    )
    async def discover_metrics(
        search: str | None = Query(default=None),
        tags: list[str] | None = Query(default=None),
        status: str | None = Query(default=None),
        metric_type: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        session: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        svc = MetricService(session)
        metrics, total = await svc.list_metrics(
            page=1,
            page_size=limit,
            search=search,
            tags=tags,
            status=status,
            metric_type=metric_type,
        )

        items = [
            {
                "name": m.name,
                "display_name": m.display_name,
                "description": m.description,
                "metric_type": (
                    m.metric_type.value
                    if hasattr(m.metric_type, "value")
                    else m.metric_type
                ),
                "owner": m.owner,
                "tags": m.tags,
            }
            for m in metrics
        ]
        return {
            "tool": "discover_metrics",
            "count": len(items),
            "total_matching": total,
            "items": items,
            "context": "Use get_metric_definition for full calculation details.",
        }

    @router.get(
        "/tools/get_metric_definition",
        operation_id="get_metric_definition",
        summary="Get full metric definition",
        description=(
            "Get the complete definition of a specific business metric including "
            "its formula, SQL expression, supported dimensions, time grains, "
            "filters, and ownership. Use this when you need to understand exactly "
            "how a metric is calculated or what dimensions are available for "
            "analysis."
        ),
    )
    async def get_metric_definition(
        metric_name: str,
        session: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        svc = MetricService(session)
        metric = await svc.get_metric_by_name(metric_name)

        dimensions = metric.dimensions or []
        dim_names = [
            d.get("name") for d in dimensions if isinstance(d, dict) and d.get("name")
        ]

        return {
            "tool": "get_metric_definition",
            "metric": {
                "name": metric.name,
                "display_name": metric.display_name,
                "description": metric.description,
                "formula": metric.formula,
                "sql_expression": metric.sql_expression,
                "metric_type": (
                    metric.metric_type.value
                    if hasattr(metric.metric_type, "value")
                    else metric.metric_type
                ),
                "time_grains": metric.time_grains,
                "default_time_grain": metric.default_time_grain,
                "dimensions": metric.dimensions,
                "filters": metric.filters,
                "owner": metric.owner,
                "owner_email": metric.owner_email,
                "source_platform": metric.source_platform,
                "source_ref": metric.source_ref,
                "tags": metric.tags,
                "status": metric.status.value
                if hasattr(metric.status, "value")
                else metric.status,
                "deprecated_reason": metric.deprecated_reason,
                "meta": metric.meta,
            },
            "context": (
                f"This metric has {len(dim_names)} available dimensions: "
                f"{', '.join(dim_names) if dim_names else 'none'}."
            ),
        }

    @router.get(
        "/tools/search_metrics",
        operation_id="search_metrics",
        summary="Search metrics by concept",
        description=(
            "Search for metrics by keyword across names, descriptions, and tags. "
            "Use this when you're not sure of the exact metric name but know the "
            "business concept you're looking for (e.g., revenue, churn, conversion)."
        ),
    )
    async def search_metrics(
        query: str,
        limit: int = Query(default=10, ge=1, le=100),
        session: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        svc = MetricService(session)
        metrics, total = await svc.list_metrics(page=1, page_size=limit, search=query)
        items = [
            {
                "name": m.name,
                "description": m.description,
                "metric_type": (
                    m.metric_type.value
                    if hasattr(m.metric_type, "value")
                    else m.metric_type
                ),
                "owner": m.owner,
                "tags": m.tags,
                "relevance": "high"
                if query.lower() in (m.name or "").lower()
                else "medium",
            }
            for m in metrics
        ]
        return {
            "tool": "search_metrics",
            "query": query,
            "count": len(items),
            "total_matching": total,
            "items": items,
        }

    @router.get(
        "/tools/get_metric_sql",
        operation_id="get_metric_sql",
        summary="Get SQL expression for a metric",
        description=(
            "Get just the SQL expression for a metric, ready to be incorporated "
            "into a query. Returns the SQL snippet, default time grain, and "
            "available dimensions. Use this when you need to build a SQL query "
            "that references this metric."
        ),
    )
    async def get_metric_sql(
        metric_name: str,
        time_grain: str | None = Query(default=None),
        session: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        svc = MetricService(session)
        metric = await svc.get_metric_by_name(metric_name)

        chosen_grain = time_grain or metric.default_time_grain
        dimensions = metric.dimensions or []
        dim_names = [
            d.get("name") for d in dimensions if isinstance(d, dict) and d.get("name")
        ]

        return {
            "tool": "get_metric_sql",
            "metric_name": metric.name,
            "sql_expression": metric.sql_expression,
            "time_grain": chosen_grain,
            "default_time_grain": metric.default_time_grain,
            "available_time_grains": metric.time_grains,
            "dimensions": metric.dimensions,
            "filters": metric.filters,
            "context": (
                f"This metric can be sliced by {len(dim_names)} dimensions: "
                f"{', '.join(dim_names) if dim_names else 'none'}."
            ),
        }

    @router.get(
        "/tools/list_collections",
        operation_id="list_collections",
        summary="List metric collections",
        description=(
            "List all metric collections (logical groupings like Revenue Metrics, "
            "Marketing KPIs). Use this to understand how metrics are organized."
        ),
    )
    async def list_collections(
        session: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        svc = CollectionService(session)
        collections = await svc.list_collections()

        items: list[dict[str, Any]] = []
        for c in collections:
            count = await svc.get_metric_count(c.id)
            items.append(
                {
                    "name": c.name,
                    "description": c.description,
                    "metric_count": count,
                }
            )

        return {
            "tool": "list_collections",
            "count": len(items),
            "items": items,
            "context": (
                "Use get_collection_metrics to inspect metrics within one collection."
            ),
        }

    @router.get(
        "/tools/get_collection_metrics",
        operation_id="get_collection_metrics",
        summary="Get all metrics in a collection",
        description=(
            "Get all metrics in a specific collection. Use this when you need all "
            "metrics related to a specific domain or team."
        ),
    )
    async def get_collection_metrics(
        collection_name: str,
        session: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        collection_svc = CollectionService(session)
        metric_svc = MetricService(session)

        collections = await collection_svc.list_collections()
        collection = next((c for c in collections if c.name == collection_name), None)
        if collection is None:
            return {
                "tool": "get_collection_metrics",
                "collection_name": collection_name,
                "count": 0,
                "items": [],
                "context": "Collection not found.",
            }

        metrics, total = await metric_svc.list_metrics(
            page=1,
            page_size=1000,
            collection_id=collection.id,
        )
        items = [
            {
                "name": m.name,
                "display_name": m.display_name,
                "description": m.description,
                "metric_type": (
                    m.metric_type.value
                    if hasattr(m.metric_type, "value")
                    else m.metric_type
                ),
                "owner": m.owner,
                "tags": m.tags,
            }
            for m in metrics
        ]

        return {
            "tool": "get_collection_metrics",
            "collection_name": collection_name,
            "count": len(items),
            "total_matching": total,
            "items": items,
            "context": f"Collection '{collection_name}' contains {len(items)} metrics.",
        }

    return router


def setup_mcp(app: FastAPI) -> None:
    """Attach MCP interfaces (auto + custom tools) to the FastAPI app."""
    if getattr(app.state, "mcp_initialized", False):
        return

    app.include_router(_create_custom_mcp_router())

    mcp = FastApiMCP(
        app,
        name="MetricStore MCP",
        description=(
            "MCP interface for discovering and querying governed business metrics "
            "from MetricStore."
        ),
        auth_config=AuthConfig(dependencies=[Depends(require_api_key)]),
    )
    mcp.mount_http(mount_path="/mcp")

    app.state.mcp_server = mcp
    app.state.mcp_initialized = True
