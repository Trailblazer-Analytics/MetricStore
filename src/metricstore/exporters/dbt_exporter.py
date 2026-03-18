"""Best-effort dbt MetricFlow YAML exporter.

Exports metric definitions only. Generated output still requires semantic_models
and measure context inside a dbt project to be executable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

from ruamel.yaml import YAML


class DbtExporter:
    """Export MetricStore metrics into best-effort dbt MetricFlow YAML."""

    _TYPE_MAP = {
        "simple": "simple",
        "derived": "derived",
        "cumulative": "cumulative",
        "conversion": "conversion",
    }

    def export(self, metrics: list[dict], version: str) -> str:
        generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        out_metrics: list[dict] = []
        for m in metrics:
            metric_type = self._TYPE_MAP.get(str(m.get("metric_type")), "simple")

            row: dict = {
                "name": m.get("name"),
                "type": metric_type,
            }
            if m.get("description"):
                row["description"] = m.get("description")

            type_params: dict = {}
            if metric_type == "simple":
                if m.get("source_ref"):
                    type_params["measure"] = m.get("source_ref")
                elif m.get("sql_expression") or m.get("formula"):
                    type_params["expr"] = m.get("sql_expression") or m.get("formula")
            else:
                expr = m.get("formula") or m.get("sql_expression")
                if expr:
                    type_params["expr"] = expr

            if type_params:
                row["type_params"] = type_params

            raw_filter = self._extract_raw_filter(m.get("filters") or [])
            if raw_filter:
                row["filter"] = raw_filter

            out_metrics.append(row)

        payload = {"metrics": out_metrics}

        yaml = YAML(typ="rt")
        yaml.default_flow_style = False

        buf = StringIO()
        yaml.dump(payload, buf)

        header = (
            "# Exported from MetricStore to dbt MetricFlow format (best effort)\n"
            f"# Generated at {generated_at} from MetricStore v{version}\n"
            "# NOTE: These metric definitions require semantic_models/measures "
            "in your dbt project.\n"
        )
        return header + buf.getvalue()

    def _extract_raw_filter(self, filters: list[dict]) -> str | None:
        for f in filters:
            if not isinstance(f, dict):
                continue
            if f.get("dimension") == "__raw_filter__":
                value = f.get("value")
                return str(value) if value is not None else None
        return None
