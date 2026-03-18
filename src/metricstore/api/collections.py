"""Collection API routes — /api/v1/collections."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from metricstore.dependencies import get_collection_service
from metricstore.schemas.collection import CollectionCreate, CollectionResponse
from metricstore.services.collection_service import CollectionService

router = APIRouter(prefix="/collections", tags=["collections"])


# ── POST /collections ─────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a collection",
    responses={409: {"description": "Name already exists"}},
)
async def create_collection(
    body: CollectionCreate,
    svc: CollectionService = Depends(get_collection_service),
) -> CollectionResponse:
    collection = await svc.create_collection(body)
    count = await svc.get_metric_count(collection.id)
    return _to_response(collection, count)


# ── GET /collections ──────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[CollectionResponse],
    summary="List all collections",
)
async def list_collections(
    svc: CollectionService = Depends(get_collection_service),
) -> list[CollectionResponse]:
    collections = await svc.list_collections()
    result = []
    for c in collections:
        count = await svc.get_metric_count(c.id)
        result.append(_to_response(c, count))
    return result


# ── GET /collections/{collection_id} ──────────────────────────────────────────

@router.get(
    "/{collection_id}",
    response_model=CollectionResponse,
    summary="Get a collection by ID",
    responses={404: {"description": "Not found"}},
)
async def get_collection(
    collection_id: UUID,
    svc: CollectionService = Depends(get_collection_service),
) -> CollectionResponse:
    collection = await svc.get_collection(collection_id)
    count = await svc.get_metric_count(collection_id)
    return _to_response(collection, count)


# ── POST /collections/{collection_id}/metrics/{metric_id} ────────────────────

@router.post(
    "/{collection_id}/metrics/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add a metric to a collection",
    responses={404: {"description": "Collection or metric not found"}, 409: {"description": "Already in collection"}},
)
async def add_metric_to_collection(
    collection_id: UUID,
    metric_id: UUID,
    svc: CollectionService = Depends(get_collection_service),
) -> None:
    await svc.add_metric_to_collection(collection_id, metric_id)


# ── DELETE /collections/{collection_id}/metrics/{metric_id} ──────────────────

@router.delete(
    "/{collection_id}/metrics/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a metric from a collection",
    responses={404: {"description": "Link not found"}},
)
async def remove_metric_from_collection(
    collection_id: UUID,
    metric_id: UUID,
    svc: CollectionService = Depends(get_collection_service),
) -> None:
    await svc.remove_metric_from_collection(collection_id, metric_id)


# ── Helper ────────────────────────────────────────────────────────────────────

def _to_response(collection: object, metric_count: int) -> CollectionResponse:
    return CollectionResponse(
        id=collection.id,  # type: ignore[attr-defined]
        name=collection.name,  # type: ignore[attr-defined]
        description=collection.description,  # type: ignore[attr-defined]
        metric_count=metric_count,
        created_at=collection.created_at,  # type: ignore[attr-defined]
        updated_at=collection.updated_at,  # type: ignore[attr-defined]
    )
