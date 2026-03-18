"""FastAPI dependency providers for services and database sessions."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from metricstore.database import AsyncSessionLocal
from metricstore.services.collection_service import CollectionService
from metricstore.services.metric_service import MetricService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for the duration of a single request."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_metric_service(
    session: AsyncSession = Depends(get_db),
) -> MetricService:
    return MetricService(session)


async def get_collection_service(
    session: AsyncSession = Depends(get_db),
) -> CollectionService:
    return CollectionService(session)
