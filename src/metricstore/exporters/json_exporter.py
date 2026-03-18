"""MetricStore native JSON exporter.

Exports full MetricStore metric objects as pretty-printed JSON with export metadata.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime


class JsonExporter:
    """Export metrics as MetricStore native JSON."""

    def export(self, metrics: list[dict], version: str) -> str:
        exported_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        payload = {
            "metadata": {
                "exported_at": exported_at,
                "source": "metricstore",
                "version": version,
                "count": len(metrics),
            },
            "metrics": metrics,
        }
        return json.dumps(payload, indent=2)
