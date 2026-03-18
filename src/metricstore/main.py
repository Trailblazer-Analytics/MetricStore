"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from metricstore.api import api_router
from metricstore.auth import initialize_auth_runtime
from metricstore.config import settings
from metricstore.mcp_server import setup_mcp

_OPENAPI_TAGS = [
    {
        "name": "metrics",
        "description": (
            "Create, read, update, delete, and search governed metric definitions. "
            "Every write operation is automatically versioned."
        ),
    },
    {
        "name": "collections",
        "description": (
            "Named groupings of metrics for organisational or thematic purposes."
        ),
    },
    {
        "name": "import/export",
        "description": (
            "Bulk import metrics from YAML/JSON files (MetricStore, dbt, Cube formats) "
            "and export the full catalog or a filtered subset."
        ),
    },
    {
        "name": "ops",
        "description": "Operational endpoints (health check, readiness).",
    },
]


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_auth_runtime()
        yield

    app = FastAPI(
        title=settings.app_name,
        description=(
            "A lightweight, tool-agnostic metrics catalog that serves governed "
            "business metric definitions via REST API and MCP server."
        ),
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=_OPENAPI_TAGS,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "code": "validation_error"},
        )

    # ── Routes ────────────────────────────────────────────────────────────────
    @app.get("/health", tags=["ops"], response_model=dict)
    async def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    app.include_router(api_router, prefix=settings.api_prefix)
    setup_mcp(app)

    return app


app = create_app()
