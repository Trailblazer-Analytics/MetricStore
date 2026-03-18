"""API router — aggregates all sub-routers."""

from fastapi import APIRouter

from metricstore.api.collections import router as collections_router
from metricstore.api.metrics import router as metrics_router

api_router = APIRouter()
api_router.include_router(metrics_router)
api_router.include_router(collections_router)
