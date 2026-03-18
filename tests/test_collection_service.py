"""Integration tests for CollectionService business logic."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException, status

from metricstore.schemas.collection import CollectionCreate
from metricstore.services.collection_service import CollectionService


@pytest.mark.asyncio
async def test_collection_service_create_list_get(async_session_factory) -> None:
    async with async_session_factory() as session:
        service = CollectionService(session)

        created = await service.create_collection(
            CollectionCreate(name="finance_core", description="Core finance KPIs")
        )

        listed = await service.list_collections()
        fetched = await service.get_collection(created.id)
        count = await service.get_metric_count(created.id)

        assert fetched.id == created.id
        assert [collection.name for collection in listed] == ["finance_core"]
        assert count == 0


@pytest.mark.asyncio
async def test_collection_service_duplicate_name(async_session_factory) -> None:
    async with async_session_factory() as session:
        service = CollectionService(session)
        payload = CollectionCreate(name="duplicate_name")

        await service.create_collection(payload)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_collection(payload)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_collection_service_add_and_remove_metric(
    async_session_factory, seeded_db
) -> None:
    async with async_session_factory() as session:
        service = CollectionService(session)
        collection = await service.create_collection(
            CollectionCreate(name="growth_kpis")
        )
        metric_id = seeded_db["metrics"]["revenue"].id

        await service.add_metric_to_collection(collection.id, metric_id)
        assert await service.get_metric_count(collection.id) == 1

        with pytest.raises(HTTPException) as exc_info:
            await service.add_metric_to_collection(collection.id, metric_id)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT

        await service.remove_metric_from_collection(collection.id, metric_id)
        assert await service.get_metric_count(collection.id) == 0


@pytest.mark.asyncio
async def test_collection_service_missing_entities(
    async_session_factory, seeded_db
) -> None:
    async with async_session_factory() as session:
        service = CollectionService(session)
        collection = await service.create_collection(CollectionCreate(name="ops_kpis"))
        metric_id = seeded_db["metrics"]["mrr"].id

        with pytest.raises(HTTPException) as missing_collection:
            await service.get_collection(UUID("00000000-0000-0000-0000-000000000001"))

        assert missing_collection.value.status_code == status.HTTP_404_NOT_FOUND

        with pytest.raises(HTTPException) as missing_metric:
            await service.add_metric_to_collection(
                collection.id,
                UUID("00000000-0000-0000-0000-000000000002"),
            )

        assert missing_metric.value.status_code == status.HTTP_404_NOT_FOUND

        with pytest.raises(HTTPException) as missing_link:
            await service.remove_metric_from_collection(collection.id, metric_id)

        assert missing_link.value.status_code == status.HTTP_404_NOT_FOUND
