"""dbt MetricFlow YAML/manifest importer.

Converts dbt semantic layer metrics into MetricStore `MetricCreate` schemas.
"""

from __future__ import annotations

import logging
from typing import Any

from ruamel.yaml import YAML

from metricstore.schemas.metric import MetricCreate

logger = logging.getLogger(__name__)


class DbtImporter:
    """Parse dbt MetricFlow files into MetricStore metric definitions."""

    _TYPE_MAP = {
        "simple": "simple",
        "derived": "derived",
        "cumulative": "cumulative",
        "conversion": "conversion",
        "ratio": "derived",
    }

    _DIM_TYPE_MAP = {
        "categorical": "categorical",
        "time": "temporal",
        "temporal": "temporal",
        "numerical": "numerical",
        "number": "numerical",
    }

    def parse_file(self, file_content: str) -> list[MetricCreate]:
        """Parse dbt MetricFlow YAML file content and return MetricCreate entries."""
        yaml = YAML(typ="safe")
        try:
            payload = yaml.load(file_content) or {}
        except Exception as exc:
            raise ValueError(f"Malformed dbt YAML: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Malformed dbt YAML: expected top-level mapping")

        semantic_models = payload.get("semantic_models") or []
        metrics = payload.get("metrics") or []

        measure_to_models, model_dimensions = self._build_semantic_indexes(
            semantic_models
        )

        by_name: dict[str, MetricCreate] = {}
        for metric in metrics:
            if not isinstance(metric, dict):
                continue

            name = metric.get("name")
            if not name:
                continue

            metric_def = self._metric_from_dbt_yaml(
                metric,
                measure_to_models=measure_to_models,
                model_dimensions=model_dimensions,
            )

            if name in by_name:
                logger.warning("Duplicate metric name '%s' found; last one wins.", name)
            by_name[name] = metric_def

        return list(by_name.values())

    def parse_manifest(self, manifest_json: dict) -> list[MetricCreate]:
        """Parse dbt compiled manifest.json and return MetricCreate entries."""
        if not isinstance(manifest_json, dict):
            raise ValueError("manifest_json must be a dictionary")

        nodes = manifest_json.get("nodes") or {}
        if not isinstance(nodes, dict):
            raise ValueError("Invalid manifest.json: nodes must be an object")

        by_name: dict[str, MetricCreate] = {}
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            if node.get("resource_type") != "metric":
                continue

            name = node.get("name")
            if not name:
                continue

            type_name = node.get("type") or node.get("calculation_method") or "simple"
            metric_type = self._TYPE_MAP.get(str(type_name).lower(), "simple")

            type_params = node.get("type_params") or {}
            measure = (
                type_params.get("measure")
                or node.get("measure")
                or node.get("depends_on", {}).get("measure")
            )

            formula = type_params.get("expr") or node.get("expression")
            filters = []
            if node.get("filter"):
                filters.append(
                    {
                        "dimension": "__raw_filter__",
                        "operator": "equals",
                        "value": str(node.get("filter")),
                    }
                )

            data = {
                "name": name,
                "description": node.get("description") or None,
                "metric_type": metric_type,
                "formula": formula,
                "source_ref": measure,
                "source_platform": "dbt",
                "tags": ["dbt-import"],
                "filters": filters,
            }

            metric_def = MetricCreate.model_validate(data)
            if name in by_name:
                logger.warning(
                    "Duplicate metric name '%s' found in manifest; last one wins.", name
                )
            by_name[name] = metric_def

        return list(by_name.values())

    def _metric_from_dbt_yaml(
        self,
        metric: dict[str, Any],
        *,
        measure_to_models: dict[str, set[str]],
        model_dimensions: dict[str, list[dict[str, Any]]],
    ) -> MetricCreate:
        name = metric.get("name")
        type_name = metric.get("type", "simple")
        metric_type = self._TYPE_MAP.get(str(type_name).lower(), "simple")

        type_params = metric.get("type_params") or {}
        measure = type_params.get("measure")
        expr = type_params.get("expr")

        referenced_models: set[str] = set()
        if measure:
            referenced_models |= measure_to_models.get(str(measure), set())

        metrics_ref = type_params.get("metrics") or []
        for ref in metrics_ref:
            ref_measure = None
            if isinstance(ref, dict):
                ref_measure = ref.get("measure") or ref.get("name")
            elif isinstance(ref, str):
                ref_measure = ref
            if ref_measure:
                referenced_models |= measure_to_models.get(str(ref_measure), set())

        dimensions = self._merge_dimensions(referenced_models, model_dimensions)
        time_grains = self._infer_time_grains(dimensions)

        filters = []
        raw_filter = metric.get("filter")
        if raw_filter:
            filters.append(
                {
                    "dimension": "__raw_filter__",
                    "operator": "equals",
                    "value": str(raw_filter).strip(),
                }
            )

        data = {
            "name": name,
            "description": metric.get("description") or None,
            "metric_type": metric_type,
            "source_ref": str(measure) if measure else None,
            "formula": str(expr) if expr else None,
            "dimensions": dimensions,
            "filters": filters,
            "time_grains": time_grains,
            "default_time_grain": time_grains[0] if time_grains else "day",
            "source_platform": "dbt",
            "tags": ["dbt-import"],
        }

        return MetricCreate.model_validate(data)

    def _build_semantic_indexes(
        self, semantic_models: list[Any]
    ) -> tuple[dict[str, set[str]], dict[str, list[dict[str, Any]]]]:
        measure_to_models: dict[str, set[str]] = {}
        model_dimensions: dict[str, list[dict[str, Any]]] = {}

        for sm in semantic_models:
            if not isinstance(sm, dict):
                continue
            model_name = sm.get("name")
            if not model_name:
                continue

            dims: list[dict[str, Any]] = []
            for dim in sm.get("dimensions") or []:
                if not isinstance(dim, dict) or not dim.get("name"):
                    continue
                dim_type = self._DIM_TYPE_MAP.get(
                    str(dim.get("type", "categorical")).lower(), "categorical"
                )
                dims.append(
                    {
                        "name": dim.get("name"),
                        "description": dim.get("description") or None,
                        "type": dim_type,
                        "time_grain": (
                            (dim.get("type_params") or {}).get("time_granularity")
                        ),
                    }
                )

            model_dimensions[str(model_name)] = dims

            for measure in sm.get("measures") or []:
                if not isinstance(measure, dict):
                    continue
                m_name = measure.get("name")
                if not m_name:
                    continue
                measure_to_models.setdefault(str(m_name), set()).add(str(model_name))

        return measure_to_models, model_dimensions

    def _merge_dimensions(
        self,
        referenced_models: set[str],
        model_dimensions: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for model in referenced_models:
            for dim in model_dimensions.get(model, []):
                name = dim.get("name")
                if not name:
                    continue
                # drop helper field before persisting into MetricStore dimensions
                payload = {
                    "name": dim.get("name"),
                    "description": dim.get("description"),
                    "type": dim.get("type", "categorical"),
                }
                merged[name] = payload

        return list(merged.values())

    def _infer_time_grains(self, dimensions: list[dict[str, Any]]) -> list[str]:
        # dbt doesn't always define a single canonical list of grains per metric,
        # so keep MetricStore defaults unless we can infer time support.
        has_temporal = any(d.get("type") == "temporal" for d in dimensions)
        if has_temporal:
            return ["day", "week", "month"]
        return ["day", "week", "month"]
