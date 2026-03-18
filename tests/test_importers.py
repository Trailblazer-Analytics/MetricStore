"""Importer tests for dbt and native YAML workflows."""

from __future__ import annotations

import pytest

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
