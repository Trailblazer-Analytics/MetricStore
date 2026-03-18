"""Metric API routes — /api/v1/metrics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from metricstore.dependencies import get_metric_service
from metricstore.exporters import DbtExporter, JsonExporter, OsiExporter, YamlExporter
from metricstore.importers import DbtImporter, MetricStoreYamlImporter
from metricstore.config import settings
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
    responses={
        200: {
            "content": {
                "application/json": {},
                "application/yaml": {},
                "text/yaml": {},
            }
        }
    },
)
async def export_metrics(
    fmt: str = Query(
        "json",
        alias="format",
        pattern="^(json|yaml|osi|dbt)$",
        description=(
            "Export format. 'osi' is experimental OSI-compatible output and may "
            "change as the OSI specification evolves."
        ),
    ),
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

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if fmt == "json":
        content = JsonExporter().export(data, settings.app_version)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="metricstore_export_{now}.json"'
            },
        )

    if fmt == "yaml":
        content = YamlExporter().export(data, settings.app_version)
        return PlainTextResponse(
            content,
            media_type="application/yaml",
            headers={
                "Content-Disposition": f'attachment; filename="metricstore_export_{now}.yaml"'
            },
        )

    if fmt == "osi":
        content = OsiExporter().export(data, settings.app_version)
        return PlainTextResponse(
            content,
            media_type="application/yaml",
            headers={
                "Content-Disposition": f'attachment; filename="metricstore_osi_export_{now}.yaml"'
            },
        )

    if fmt == "dbt":
        content = DbtExporter().export(data, settings.app_version)
        return PlainTextResponse(
            content,
            media_type="application/yaml",
            headers={
                "Content-Disposition": f'attachment; filename="metricstore_dbt_export_{now}.yaml"'
            },
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported export format '{fmt}'.",
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
    files: list[UploadFile] | None = File(default=None, description="One or more files"),
    file: UploadFile | None = File(default=None, description="Single file (legacy clients)"),
    fmt: str = Query(
        "metricstore",
        alias="format",
        pattern="^(metricstore|dbt|cube)$",
        description="Source format",
    ),
    svc: MetricService = Depends(get_metric_service),
) -> ImportResult:
    if fmt == "cube":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="'cube' importer is not yet implemented.",
        )

    upload_files: list[UploadFile] = list(files or [])
    if file is not None:
        upload_files.append(file)
    if not upload_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file uploaded. Provide 'file' or 'files'.",
        )

    imported = updated = skipped = 0
    errors: list[str] = []

    dbt_importer = DbtImporter()
    yaml_importer = MetricStoreYamlImporter()

    parsed_metrics: list[MetricCreate] = []

    for up in upload_files:
        raw = await up.read()
        filename = (up.filename or "").lower()
        text_content = raw.decode("utf-8", errors="replace")

        try:
            if fmt == "dbt":
                if filename.endswith("manifest.json") or filename.endswith(".json"):
                    manifest = json.loads(text_content)
                    parsed_metrics.extend(dbt_importer.parse_manifest(manifest))
                else:
                    parsed_metrics.extend(dbt_importer.parse_file(text_content))
            else:
                parsed_metrics.extend(yaml_importer.parse_file(text_content))
        except Exception as exc:
            errors.append(f"{up.filename or 'uploaded file'}: {exc}")

    for data in parsed_metrics:
        try:
            await svc.create_metric(data)
            imported += 1
            continue
        except HTTPException as exc:
            if exc.status_code != status.HTTP_409_CONFLICT:
                errors.append(f"{data.name}: {exc.detail}")
                continue

        # Upsert path: metric already exists -> update by name.
        try:
            existing = await svc.get_metric_by_name(data.name)
            patch_data = data.model_dump(exclude={"name"})
            await svc.update_metric(existing.id, MetricUpdate.model_validate(patch_data))
            updated += 1
        except Exception as exc:
            skipped += 1
            errors.append(f"{data.name}: failed to update existing metric ({exc})")

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
