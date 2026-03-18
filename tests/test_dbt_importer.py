"""Tests for dbt MetricFlow importer."""

from __future__ import annotations

import pytest

from metricstore.importers.dbt_importer import DbtImporter


REALISTIC_DBT_YAML = """
semantic_models:
  - name: orders
    defaults:
      agg_time_dimension: order_date
    entities:
      - name: order_id
        type: primary
    measures:
      - name: order_total
        agg: sum
        expr: amount
      - name: order_count
        agg: count
        expr: "1"
    dimensions:
      - name: order_date
        type: time
        type_params:
          time_granularity: day
      - name: region
        type: categorical

  - name: subscriptions
    defaults:
      agg_time_dimension: subscription_date
    measures:
      - name: mrr
        agg: sum
        expr: monthly_amount
    dimensions:
      - name: subscription_date
        type: time
        type_params:
          time_granularity: month
      - name: plan_tier
        type: categorical

metrics:
  - name: revenue
    description: "Total revenue from orders"
    type: simple
    type_params:
      measure: order_total
    filter: |
      {{ Dimension('order__is_completed') }} = true

  - name: blended_revenue
    type: ratio
    type_params:
      expr: revenue / order_count
      metrics:
        - name: revenue
        - name: order_count

  - name: mrr_growth
    type: derived
    type_params:
      expr: mrr - lag_mrr
      metrics:
        - name: mrr
        - name: lag_mrr
"""

CROSS_MODEL_DBT_YAML = """
semantic_models:
  - name: orders
    measures:
      - name: order_total
        agg: sum
        expr: amount
    dimensions:
      - name: region
        type: categorical

  - name: ad_spend
    measures:
      - name: ad_cost
        agg: sum
        expr: spend
    dimensions:
      - name: channel
        type: categorical

metrics:
  - name: roas_like_metric
    type: derived
    type_params:
      expr: order_total / ad_cost
      metrics:
        - name: order_total
        - name: ad_cost
"""


def test_parse_realistic_multi_model_dbt_yaml() -> None:
    importer = DbtImporter()
    metrics = importer.parse_file(REALISTIC_DBT_YAML)

    by_name = {m.name: m for m in metrics}
    assert set(by_name.keys()) == {"revenue", "blended_revenue", "mrr_growth"}

    revenue = by_name["revenue"]
    assert revenue.source_platform == "dbt"
    assert revenue.source_ref == "order_total"
    assert revenue.metric_type == "simple"
    assert revenue.tags == ["dbt-import"]
    assert len(revenue.filters) == 1
    assert revenue.filters[0].dimension == "__raw_filter__"
    assert "is_completed" in str(revenue.filters[0].value)
    assert any(d.name == "order_date" and d.type == "temporal" for d in revenue.dimensions)
    assert any(d.name == "region" for d in revenue.dimensions)


def test_parse_metrics_across_semantic_models() -> None:
    importer = DbtImporter()
    metrics = importer.parse_file(CROSS_MODEL_DBT_YAML)

    assert len(metrics) == 1
    metric = metrics[0]
    names = {d.name for d in metric.dimensions}

    # Dimensions from both semantic models should be present.
    assert names == {"region", "channel"}


def test_parse_derived_metric_formula_from_expr() -> None:
    importer = DbtImporter()
    metrics = importer.parse_file(REALISTIC_DBT_YAML)
    by_name = {m.name: m for m in metrics}

    blended = by_name["blended_revenue"]
    assert blended.metric_type == "derived"
    assert blended.formula == "revenue / order_count"


def test_malformed_yaml_raises_value_error() -> None:
    importer = DbtImporter()
    with pytest.raises(ValueError, match="Malformed dbt YAML"):
        importer.parse_file("metrics: [\n  - name: foo\n    type: simple\n")


def test_duplicate_metric_names_last_one_wins(caplog: pytest.LogCaptureFixture) -> None:
    importer = DbtImporter()
    payload = """
metrics:
  - name: revenue
    description: old
    type: simple
    type_params:
      measure: order_total
  - name: revenue
    description: new
    type: simple
    type_params:
      measure: order_total
"""
    metrics = importer.parse_file(payload)

    assert len(metrics) == 1
    assert metrics[0].description == "new"
    assert "last one wins" in caplog.text
