"""Importer for MetricStore native YAML format."""

from __future__ import annotations

from typing import Any

from ruamel.yaml import YAML

from metricstore.schemas.metric import MetricCreate


class MetricStoreYamlImporter:
    """Parse MetricStore's canonical YAML format into MetricCreate entries."""

    def parse_file(self, file_content: str) -> list[MetricCreate]:
        yaml = YAML(typ="safe")
        try:
            payload = yaml.load(file_content) or {}
        except Exception as exc:
            raise ValueError(f"Malformed MetricStore YAML: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Malformed MetricStore YAML: expected top-level mapping")

        metrics = payload.get("metrics")
        if metrics is None:
            return []
        if not isinstance(metrics, list):
            raise ValueError("Malformed MetricStore YAML: 'metrics' must be a list")

        out: list[MetricCreate] = []
        for i, row in enumerate(metrics):
            if not isinstance(row, dict):
                raise ValueError(f"Malformed MetricStore YAML: metrics[{i}] must be an object")

            normalized: dict[str, Any] = dict(row)
            if normalized.get("description") == "":
                normalized["description"] = None

            out.append(MetricCreate.model_validate(normalized))

        return out
