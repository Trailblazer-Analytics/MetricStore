"""Shared / utility schemas used across multiple endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None


class ImportResult(BaseModel):
    imported: int
    updated: int
    skipped: int
    errors: list[str] = []
