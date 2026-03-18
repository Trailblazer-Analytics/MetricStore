"""Importer tests for dbt and native YAML workflows."""

from __future__ import annotations

import pytest

from metricstore.exporters.dbt_exporter import DbtExporter
from metricstore.exporters.osi_exporter import OsiExporter
from metricstore.exporters.yaml_exporter import YamlExporter
from metricstore.importers.dbt_importer import DbtImporter
from metricstore.importers.yaml_importer import MetricStoreYamlImporter

DBT_REALISTIC = """
semantic_models:
  - name: orders
    measures:
      - name: order_total
        agg: sum
        expr: amount
    dimensions:
      - name: order_date
        type: time
        type_params:
          time_granularity: day
      - name: region
        type: categorical
  - name: subscriptions
    measures:
      - name: mrr_measure
        agg: sum
        expr: mrr_amount
    dimensions:
      - name: plan_tier
        type: categorical
metrics:
  - name: revenue
    description: Total revenue from orders
    type: simple
    type_params:
      measure: order_total
  - name: blended_growth
    type: derived
    type_params:
      expr: revenue / mrr_measure
      metrics:
        - name: revenue
        - name: mrr_measure
"""


def test_dbt_yaml_import() -> None:
    importer = DbtImporter()
    metrics = importer.parse_file(DBT_REALISTIC)
    by_name = {m.name: m for m in metrics}

    assert "revenue" in by_name
    assert by_name["revenue"].metric_type == "simple"
    assert by_name["revenue"].source_ref == "order_total"
    assert by_name["revenue"].source_platform == "dbt"


def test_dbt_derived_metrics() -> None:
    importer = DbtImporter()
    metrics = importer.parse_file(DBT_REALISTIC)
    by_name = {m.name: m for m in metrics}

    assert by_name["blended_growth"].metric_type == "derived"
    assert by_name["blended_growth"].formula == "revenue / mrr_measure"


def test_dbt_malformed_yaml() -> None:
    importer = DbtImporter()
    with pytest.raises(ValueError):
        importer.parse_file("metrics: [\n - name: broken")


def test_native_yaml_import() -> None:
    rows = [
        {
            "name": "monthly_revenue",
            "display_name": "Monthly Revenue",
            "description": "Total revenue aggregated monthly",
            "formula": "SUM(order_total)",
            "sql_expression": "SUM(orders.amount)",
            "metric_type": "simple",
            "time_grains": ["day", "week", "month"],
            "default_time_grain": "month",
            "dimensions": [
                {
                    "name": "region",
                    "description": "Sales region",
                    "type": "categorical",
                }
            ],
            "tags": ["revenue", "finance"],
            "status": "active",
        }
    ]

    exported = YamlExporter().export(rows, "0.1.0")
    parsed = MetricStoreYamlImporter().parse_file(exported)

    assert len(parsed) == 1
    assert parsed[0].name == "monthly_revenue"
    assert parsed[0].default_time_grain == "month"


def test_native_yaml_import_normalizes_empty_description() -> None:
    importer = MetricStoreYamlImporter()
    parsed = importer.parse_file(
        """
metrics:
  - name: normalized_description
    metric_type: simple
    description: ""
"""
    )

    assert parsed[0].description is None


def test_native_yaml_import_rejects_non_mapping_payload() -> None:
    importer = MetricStoreYamlImporter()

    with pytest.raises(ValueError, match="top-level mapping"):
        importer.parse_file("- just\n- a\n- list\n")


def test_native_yaml_import_rejects_non_list_metrics() -> None:
    importer = MetricStoreYamlImporter()

    with pytest.raises(ValueError, match="'metrics' must be a list"):
        importer.parse_file("metrics: {}\n")


def test_native_yaml_import_rejects_non_object_metric_rows() -> None:
    importer = MetricStoreYamlImporter()

    with pytest.raises(ValueError, match=r"metrics\[0\] must be an object"):
        importer.parse_file("metrics:\n  - bad_row\n")


def test_dbt_exporter_covers_simple_derived_and_filter_paths() -> None:
    exporter = DbtExporter()
    content = exporter.export(
        [
            {
                "name": "bookings",
                "metric_type": "simple",
                "description": "Booked revenue",
                "source_ref": "booking_amount",
                "filters": [{"dimension": "__raw_filter__", "value": "is_paid = true"}],
            },
            {
                "name": "margin_rate",
                "metric_type": "derived",
                "formula": "profit / revenue",
                "filters": ["skip-me"],
            },
            {
                "name": "fallback_expr",
                "metric_type": "simple",
                "sql_expression": "SUM(amount)",
            },
        ],
        "1.2.3",
    )

    assert "type: simple" in content
    assert "measure: booking_amount" in content
    assert "filter: is_paid = true" in content
    assert "expr: profit / revenue" in content
    assert "expr: SUM(amount)" in content


def test_osi_exporter_picks_temporal_dimension_and_defaults() -> None:
    exporter = OsiExporter()
    content = exporter.export(
        [
            {
                "name": "orders",
                "metric_type": "simple",
                "sql_expression": "COUNT(*)",
                "dimensions": [
                    {"name": "region", "type": "categorical"},
                    {"name": "order_date", "type": "temporal"},
                ],
                "tags": ["ops"],
                "owner": "Analytics",
            },
            {
                "name": "conversion_rate",
                "metric_type": "conversion",
                "formula": "won / leads",
                "dimensions": [],
            },
        ],
        "2.0.0",
    )

    assert "time_dimension: order_date" in content
    assert "default_granularity: day" in content
    assert "- day" in content
    assert "type: calculated" in content


@pytest.mark.asyncio
async def test_import_upsert(test_client, seeded_db) -> None:
    first = """
metrics:
  - name: churn_rate
    description: Monthly customer churn percentage.
    metric_type: derived
    formula: churned_customers / starting_customers
    tags: [retention]
"""

    second = """
metrics:
  - name: churn_rate
    description: Updated churn definition from import.
    metric_type: derived
    formula: churned_customers / starting_customers
    tags: [retention, revised]
"""

    r1 = await test_client.post(
        "/api/v1/metrics/import?format=metricstore",
        files={"file": ("metrics.yml", first.encode("utf-8"), "text/yaml")},
    )
    assert r1.status_code == 200

    r2 = await test_client.post(
        "/api/v1/metrics/import?format=metricstore",
        files={"file": ("metrics.yml", second.encode("utf-8"), "text/yaml")},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["updated"] >= 1

    chk = await test_client.get("/api/v1/metrics/churn_rate")
    assert chk.status_code == 200
    assert "Updated churn definition" in chk.json()["description"]
