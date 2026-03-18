"""MetricVersion response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    metric_id: UUID
    version_number: int
    snapshot: dict[str, Any]
    change_summary: str | None
    changed_by: str | None
    created_at: datetime


class VersionList(BaseModel):
    items: list[VersionResponse]
    total: int
