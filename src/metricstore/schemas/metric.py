"""Metric request/response schemas."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


# ── Supporting schemas ────────────────────────────────────────────────────────

class DimensionSchema(BaseModel):
    name: str
    description: str | None = None
    type: Literal["categorical", "temporal", "numerical"] = "categorical"


class FilterSchema(BaseModel):
    dimension: str
    operator: Literal[
        "equals", "not_equals", "greater_than", "less_than", "in", "not_in"
    ]
    value: Any


# ── Base ──────────────────────────────────────────────────────────────────────

class MetricBase(BaseModel):
    name: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str | None = None
    description: str | None = None
    formula: str | None = None
    sql_expression: str | None = None
    metric_type: Literal["simple", "derived", "cumulative", "conversion"] = "simple"
    time_grains: list[str] = Field(default_factory=lambda: ["day", "week", "month"])
    default_time_grain: str = "day"
    dimensions: list[DimensionSchema] = Field(default_factory=list)
    filters: list[FilterSchema] = Field(default_factory=list)
    owner: str | None = None
    owner_email: EmailStr | None = None
    source_platform: str | None = None
    source_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    status: Literal["active", "draft", "deprecated"] = "active"
    deprecated_reason: str | None = None

    @field_validator("default_time_grain")
    @classmethod
    def default_grain_must_be_in_time_grains(cls, v: str, info: Any) -> str:
        grains = (info.data or {}).get("time_grains")
        if grains and v not in grains:
            raise ValueError(
                f"default_time_grain '{v}' must be one of time_grains {grains}"
            )
        return v


# ── Create ────────────────────────────────────────────────────────────────────

class MetricCreate(MetricBase):
    """All fields from MetricBase; `name` is required."""


# ── Partial update ────────────────────────────────────────────────────────────

class MetricUpdate(BaseModel):
    """
    All fields optional for PATCH semantics.

    Fields that are *not supplied* by the caller are absent from
    model.model_fields_set, so the service layer can distinguish
    "caller set this to None" from "caller didn't touch this field".
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str | None = None
    description: str | None = None
    formula: str | None = None
    sql_expression: str | None = None
    metric_type: Literal["simple", "derived", "cumulative", "conversion"] | None = None
    time_grains: list[str] | None = None
    default_time_grain: str | None = None
    dimensions: list[DimensionSchema] | None = None
    filters: list[FilterSchema] | None = None
    owner: str | None = None
    owner_email: EmailStr | None = None
    source_platform: str | None = None
    source_ref: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None
    status: Literal["active", "draft", "deprecated"] | None = None
    deprecated_reason: str | None = None

    @model_validator(mode="after")
    def default_grain_consistent(self) -> "MetricUpdate":
        if (
            self.default_time_grain is not None
            and self.time_grains is not None
            and self.default_time_grain not in self.time_grains
        ):
            raise ValueError(
                f"default_time_grain '{self.default_time_grain}' must be one of"
                f" time_grains {self.time_grains}"
            )
        return self


# ── Response ──────────────────────────────────────────────────────────────────

class MetricResponse(MetricBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


# ── Summary (list endpoints) ──────────────────────────────────────────────────

class MetricSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str | None
    description: str | None
    metric_type: str
    owner: str | None
    status: str
    tags: list[str]
    updated_at: datetime

    @field_validator("description", mode="before")
    @classmethod
    def truncate_description(cls, v: str | None) -> str | None:
        if v and len(v) > 200:
            return v[:197] + "..."
        return v


# ── Paginated list ────────────────────────────────────────────────────────────

class MetricList(BaseModel):
    items: list[MetricSummary]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(
        cls, items: list[MetricSummary], total: int, page: int, page_size: int
    ) -> "MetricList":
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)) if page_size else 1,
        )
