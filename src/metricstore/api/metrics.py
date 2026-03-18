"""Metric API routes — /api/v1/metrics."""

from __future__ import annotations

import json
from io import StringIO
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import PlainTextResponse
from ruamel.yaml import YAML
from pydantic import BaseModel

from metricstore.dependencies import get_metric_service
from metricstore.schemas.common import ImportResult
from metricstore.schemas.metric import (
    MetricCreate,
    MetricList,
    MetricResponse,
    MetricSummary,
    MetricUpdate,
)
from metricstore.schemas.version import VersionList, VersionResponse
from metricstore.services.metric_service import MetricService

router = APIRouter(prefix="/metrics", tags=["metrics"])

_yaml = YAML()
_yaml.default_flow_style = False


# ── Export filter body (optional) ────────────────────────────────────────────


class ExportFilter(BaseModel):
    tags: list[str] | None = None
    status: str | None = None
    collection_id: UUID | None = None


# ── POST /metrics ─────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=MetricResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a metric",
    responses={409: {"description": "Name already exists"}},
)
async def create_metric(
    body: MetricCreate,
    svc: MetricService = Depends(get_metric_service),
) -> MetricResponse:
    metric = await svc.create_metric(body)
    return MetricResponse.model_validate(metric)


# ── POST /metrics/export  (must be registered before /{metric_id_or_name}) ───

@router.post(
    "/export",
    summary="Export metrics",
    tags=["import/export"],
    responses={200: {"content": {"application/json": {}, "application/yaml": {}}}},
)
async def export_metrics(
    fmt: str = Query("json", alias="format", pattern="^(json|yaml)$"),
    body: ExportFilter = Body(default_factory=ExportFilter),
    svc: MetricService = Depends(get_metric_service),
) -> Response:
    metrics, _ = await svc.list_metrics(
        page=1,
        page_size=10_000,
        tags=body.tags,
        status=body.status,
        collection_id=body.collection_id,
    )

    data: list[dict[str, Any]] = [
        MetricResponse.model_validate(m).model_dump(mode="json") for m in metrics
    ]

    if fmt == "yaml":
        buf = StringIO()
        _yaml.dump({"metrics": data}, buf)
        return PlainTextResponse(buf.getvalue(), media_type="application/yaml")

    return Response(
        content=json.dumps({"metrics": data}, indent=2, default=str),
        media_type="application/json",
    )


# ── POST /metrics/import ──────────────────────────────────────────────────────

@router.post(
    "/import",
    response_model=ImportResult,
    summary="Import metrics from file",
    tags=["import/export"],
    responses={
        400: {"description": "Malformed file"},
        501: {"description": "Importer not yet implemented"},
    },
)
async def import_metrics(
    file: UploadFile = File(..., description="JSON or YAML file"),
    fmt: str = Query(
        "metricstore",
        alias="format",
        pattern="^(metricstore|dbt|cube)$",
        description="Source format",
    ),
    svc: MetricService = Depends(get_metric_service),
) -> ImportResult:
    if fmt in ("dbt", "cube"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"'{fmt}' importer is not yet implemented.",
        )

    raw = await file.read()
    filename = file.filename or ""

    # Auto-detect JSON vs YAML from filename extension or first byte
    try:
        if filename.endswith(".json") or raw.lstrip()[:1] in (b"{", b"["):
            payload: dict[str, Any] = json.loads(raw)
        else:
            _y = YAML()
            payload = _y.load(raw.decode())
    except Exception as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse file: {exc}",
        )

    # Support both {"metrics": [...]} wrapper and bare lists
    rows: list[Any] = payload.get("metrics", payload) if isinstance(payload, dict) else payload

    imported = updated = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(rows):
        try:
            data = MetricCreate.model_validate(row)
        except Exception as exc:
            errors.append(f"Row {i}: validation error — {exc}")
            continue
        try:
            await svc.create_metric(data)
            imported += 1
        except Exception as exc:
            # 409 = already exists → treat as skip
            if getattr(getattr(exc, "status_code", None), "real", 409) == 409 or (
                hasattr(exc, "status_code") and exc.status_code == 409
            ):
                skipped += 1
            else:
                errors.append(f"Row {i} ({row.get('name', '?')}): {exc}")

    return ImportResult(imported=imported, updated=updated, skipped=skipped, errors=errors)


# ── GET /metrics ──────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=MetricList,
    summary="List metrics",
)
async def list_metrics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, description="Full-text search across name and description"),
    tags: str | None = Query(None, description="Comma-separated tag names"),
    status: str | None = Query(None),
    metric_type: str | None = Query(None),
    owner: str | None = Query(None),
    collection_id: UUID | None = Query(None),
    svc: MetricService = Depends(get_metric_service),
) -> MetricList:
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    metrics, total = await svc.list_metrics(
        page=page,
        page_size=page_size,
        search=search,
        tags=tag_list,
        status=status,
        metric_type=metric_type,
        owner=owner,
        collection_id=collection_id,
    )
    items = [MetricSummary.model_validate(m) for m in metrics]
    return MetricList.build(items, total, page, page_size)


# ── GET /metrics/{metric_id_or_name} ─────────────────────────────────────────

@router.get(
    "/{metric_id_or_name}",
    response_model=MetricResponse,
    summary="Get a metric by ID or name",
)
async def get_metric(
    metric_id_or_name: str,
    svc: MetricService = Depends(get_metric_service),
) -> MetricResponse:
    try:
        uid = UUID(metric_id_or_name)
        metric = await svc.get_metric(uid)
    except ValueError:
        metric = await svc.get_metric_by_name(metric_id_or_name)
    return MetricResponse.model_validate(metric)


# ── PUT /metrics/{metric_id} ──────────────────────────────────────────────────

@router.put(
    "/{metric_id}",
    response_model=MetricResponse,
    summary="Update a metric",
    responses={404: {"description": "Not found"}, 409: {"description": "Name conflict"}},
)
async def update_metric(
    metric_id: UUID,
    body: MetricUpdate,
    svc: MetricService = Depends(get_metric_service),
) -> MetricResponse:
    metric = await svc.update_metric(metric_id, body)
    return MetricResponse.model_validate(metric)


# ── DELETE /metrics/{metric_id} ───────────────────────────────────────────────

@router.delete(
    "/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a metric",
    responses={404: {"description": "Not found"}},
)
async def delete_metric(
    metric_id: UUID,
    svc: MetricService = Depends(get_metric_service),
) -> None:
    await svc.delete_metric(metric_id)


# ── GET /metrics/{metric_id}/versions ─────────────────────────────────────────

@router.get(
    "/{metric_id}/versions",
    response_model=VersionList,
    summary="List all versions of a metric",
)
async def list_versions(
    metric_id: UUID,
    svc: MetricService = Depends(get_metric_service),
) -> VersionList:
    versions = await svc.get_versions(metric_id)
    items = [VersionResponse.model_validate(v) for v in versions]
    return VersionList(items=items, total=len(items))


# ── GET /metrics/{metric_id}/versions/{version_number} ────────────────────────

@router.get(
    "/{metric_id}/versions/{version_number}",
    response_model=VersionResponse,
    summary="Get a specific version of a metric",
)
async def get_version(
    metric_id: UUID,
    version_number: int,
    svc: MetricService = Depends(get_metric_service),
) -> VersionResponse:
    version = await svc.get_version(metric_id, version_number)
    return VersionResponse.model_validate(version)
