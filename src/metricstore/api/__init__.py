"""API router — aggregates all sub-routers."""

from fastapi import APIRouter, Depends

from metricstore.api.collections import router as collections_router
from metricstore.api.metrics import router as metrics_router
from metricstore.auth import require_api_key

api_router = APIRouter(dependencies=[Depends(require_api_key)])
api_router.include_router(metrics_router)
api_router.include_router(collections_router)
