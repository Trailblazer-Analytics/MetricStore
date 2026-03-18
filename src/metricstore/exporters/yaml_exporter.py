"""MetricStore native YAML exporter.

Exports metrics in the canonical MetricStore YAML import format:

metrics:
  - ...
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

from ruamel.yaml import YAML


class YamlExporter:
    """Export metrics as MetricStore native YAML."""

    def export(self, metrics: list[dict], version: str) -> str:
        exported_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        yaml = YAML(typ="rt")
        yaml.default_flow_style = False

        buf = StringIO()
        yaml.dump({"metrics": metrics}, buf)

        header = f"# Exported from MetricStore v{version} on {exported_at}\n"
        return header + buf.getvalue()
