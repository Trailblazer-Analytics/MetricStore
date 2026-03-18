"""OSI-compatible exporter (EXPERIMENTAL).

This exporter maps MetricStore metrics into a best-effort, vendor-neutral semantic
interchange structure inspired by the evolving OSI initiative.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

from ruamel.yaml import YAML


class OsiExporter:
    """Export metrics in an experimental OSI-like semantic interchange YAML format."""

    _TYPE_MAP = {
        "simple": "measure",
        "derived": "calculated",
        "cumulative": "cumulative",
        "conversion": "calculated",
    }

    def export(self, metrics: list[dict], version: str) -> str:
        generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        osi_metrics: list[dict] = []
        for m in metrics:
            dimensions = m.get("dimensions") or []
            time_dim = self._pick_time_dimension(dimensions)
            osi_metrics.append(
                {
                    "name": m.get("name"),
                    "description": m.get("description"),
                    "type": self._TYPE_MAP.get(str(m.get("metric_type")), "measure"),
                    "expression": m.get("sql_expression") or m.get("formula"),
                    "time_dimension": time_dim,
                    "granularities": m.get("time_grains") or ["day", "week", "month"],
                    "default_granularity": m.get("default_time_grain") or "day",
                    "dimensions": dimensions,
                    "tags": m.get("tags") or [],
                    "owner": {
                        "name": m.get("owner"),
                        "email": m.get("owner_email"),
                    },
                    "metadata": {
                        "source_platform": m.get("source_platform"),
                        "metricstore_id": m.get("id"),
                        "metricstore_version": version,
                    },
                }
            )

        payload = {
            "osi_version": "0.1",
            "generator": "metricstore",
            "generated_at": generated_at,
            "semantic_model": {
                "metrics": osi_metrics,
            },
        }

        yaml = YAML(typ="rt")
        yaml.default_flow_style = False
        buf = StringIO()
        yaml.dump(payload, buf)

        warning = (
            "# OSI Semantic Interchange Format (experimental)\n"
            "# WARNING: Best-effort mapping while the OSI spec is still evolving.\n"
        )
        return warning + buf.getvalue()

    def _pick_time_dimension(self, dimensions: list[dict]) -> str | None:
        for d in dimensions:
            if isinstance(d, dict) and str(d.get("type")) == "temporal":
                return d.get("name")
        return None
