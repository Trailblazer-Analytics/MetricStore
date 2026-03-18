"""Pytest fixtures for unit and integration tests.

- Unit tests: lightweight SQLite async engine.
- Integration tests: PostgreSQL async engine (expected via docker service).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure all model tables are registered in metadata before create_all/drop_all.
import metricstore.models.collection  # noqa: F401
import metricstore.models.metric  # noqa: F401
import metricstore.models.metric_collection  # noqa: F401
import metricstore.models.metric_version  # noqa: F401
from metricstore.config import settings
from metricstore.dependencies import get_db
from metricstore.main import create_app
from metricstore.models.base import Base
from metricstore.schemas.metric import MetricCreate
from metricstore.services.metric_service import MetricService

SQLITE_TEST_URL = "sqlite+aiosqlite:///:memory:"
POSTGRES_TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://metricstore:metricstore@localhost:5432/metricstore",
)


@pytest.fixture(autouse=True)
def _disable_auth_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default all tests to auth-disabled unless a test overrides it."""
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "api_keys", "")


# ---------------------------------------------------------------------------
# Unit-test DB: SQLite (speed)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def sqlite_engine():
    engine = create_async_engine(SQLITE_TEST_URL, future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def sqlite_async_session(sqlite_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(
        sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Integration-test DB: PostgreSQL (docker service)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def integration_engine():
    engine = create_async_engine(POSTGRES_TEST_URL, future=True)

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL integration DB is unavailable: {exc}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def async_session_factory(integration_engine) -> async_sessionmaker[AsyncSession]:
    """Create independent async sessions for integration tests."""
    return async_sessionmaker(
        integration_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def async_session(
    async_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Primary async DB session fixture (integration)."""
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(async_session_factory: async_sessionmaker[AsyncSession]) -> dict:
    """Seed 8 realistic business metrics for integration tests."""
    async with async_session_factory() as session:
        svc = MetricService(session)

        seeds = [
            {
                "name": "revenue",
                "display_name": "Revenue",
                "description": "Total booked revenue.",
                "metric_type": "simple",
                "sql_expression": "SUM(order_amount)",
                "tags": ["finance", "revenue"],
                "owner": "Finance Analytics",
                "status": "active",
            },
            {
                "name": "churn_rate",
                "display_name": "Churn Rate",
                "description": "Monthly customer churn percentage.",
                "metric_type": "derived",
                "formula": "churned_customers / starting_customers",
                "tags": ["retention", "customer"],
                "owner": "Growth Analytics",
                "status": "active",
            },
            {
                "name": "cac",
                "display_name": "Customer Acquisition Cost",
                "description": "Cost to acquire one customer.",
                "metric_type": "derived",
                "formula": "sales_and_marketing_spend / new_customers",
                "tags": ["marketing", "finance"],
                "owner": "Marketing Ops",
                "status": "active",
            },
            {
                "name": "conversion_rate",
                "display_name": "Conversion Rate",
                "description": "Lead to customer conversion rate.",
                "metric_type": "conversion",
                "formula": "converted_leads / total_leads",
                "tags": ["marketing", "growth"],
                "owner": "Growth Analytics",
                "status": "active",
            },
            {
                "name": "nps_score",
                "display_name": "NPS Score",
                "description": "Net promoter score from surveys.",
                "metric_type": "simple",
                "tags": ["customer", "support"],
                "owner": "Customer Success",
                "status": "draft",
            },
            {
                "name": "mrr",
                "display_name": "Monthly Recurring Revenue",
                "description": "MRR from active subscriptions.",
                "metric_type": "cumulative",
                "tags": ["revenue", "saas"],
                "owner": "Finance Analytics",
                "status": "active",
            },
            {
                "name": "dau",
                "display_name": "Daily Active Users",
                "description": "Unique active users per day.",
                "metric_type": "simple",
                "tags": ["product", "engagement"],
                "owner": "Product Analytics",
                "status": "active",
            },
            {
                "name": "arpu",
                "display_name": "Average Revenue Per User",
                "description": "Average revenue per active user.",
                "metric_type": "derived",
                "formula": "revenue / dau",
                "tags": ["revenue", "product"],
                "owner": "Finance Analytics",
                "status": "deprecated",
            },
        ]

        created = {}
        for row in seeds:
            data = MetricCreate.model_validate(row)
            metric = await svc.create_metric(data)
            created[data.name] = metric

    return {"metrics": created}


@pytest_asyncio.fixture
async def test_client(
    async_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """Async FastAPI client bound to integration DB session."""

    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()
