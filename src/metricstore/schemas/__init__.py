"""Pydantic v2 request/response schemas — public re-exports."""

from metricstore.schemas.collection import CollectionCreate, CollectionResponse
from metricstore.schemas.common import ErrorResponse, HealthResponse, ImportResult
from metricstore.schemas.metric import (
    DimensionSchema,
    FilterSchema,
    MetricBase,
    MetricCreate,
    MetricList,
    MetricResponse,
    MetricSummary,
    MetricUpdate,
)
from metricstore.schemas.version import VersionList, VersionResponse

__all__ = [
    # metric
    "DimensionSchema",
    "FilterSchema",
    "MetricBase",
    "MetricCreate",
    "MetricList",
    "MetricResponse",
    "MetricSummary",
    "MetricUpdate",
    # version
    "VersionList",
    "VersionResponse",
    # collection
    "CollectionCreate",
    "CollectionResponse",
    # common
    "ErrorResponse",
    "HealthResponse",
    "ImportResult",
]
