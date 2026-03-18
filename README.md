# MetricStore

> The open-source metrics catalog. Define your business metrics once, serve them everywhere - to AI agents, BI tools, and applications.

MetricStore is a Python/FastAPI service that combines a governed metrics registry, a REST API, and an MCP (Model Context Protocol) endpoint in one deployable process.

## The Problem

Most teams define the same metric in multiple places: dbt docs, BI semantic layers, notebooks, dashboards, and code. Over time, those definitions drift. "Revenue" in one tool may not be the same as "revenue" in another, even when the name is identical.

AI agents make this worse when they do not have a trusted source of metric definitions. They can produce plausible but incorrect formulas, dimensions, and SQL expressions, especially when asked to reason over business KPIs without access to governed metadata.

Existing solutions are often all-or-nothing platforms. They can work well, but they may require adopting a full stack, changing workflows, or paying for capabilities you do not need. MetricStore is intentionally small and composable: bring your own warehouse, BI, and orchestration tools.

## What MetricStore Does

MetricStore is a lightweight, tool-agnostic metrics registry with a REST API and MCP (Model Context Protocol) server. Define your metrics in one place and expose them to:

- 🤖 AI agents (via MCP - works with Claude, Cursor, VS Code, etc.)
- 📊 BI tools (via REST API)
- 🔧 Data pipelines (via YAML export)
- 👥 Your team (via web UI - coming soon)

## Quick Start (5 minutes)

### 1) Start MetricStore with Docker Compose

```bash
docker compose up -d --build
```

This starts:

- Postgres on `localhost:5432`
- MetricStore API + MCP on `http://localhost:8000`

### 2) Create your first metric

```bash
curl -X POST "http://localhost:8000/api/v1/metrics" \
	-H "Content-Type: application/json" \
	-d '{
		"name": "monthly_revenue",
		"display_name": "Monthly Revenue",
		"description": "Total booked revenue per month",
		"metric_type": "simple",
		"sql_expression": "SUM(order_amount)",
		"time_grains": ["day", "week", "month"],
		"default_time_grain": "month",
		"dimensions": [{"name": "region", "type": "categorical"}],
		"tags": ["finance", "revenue"],
		"status": "active"
	}'
```

### 3) Query it over MCP (JSON-RPC)

Initialize a session:

```bash
curl -i -X POST "http://localhost:8000/mcp" \
	-H "accept: application/json, text/event-stream" \
	-H "Content-Type: application/json" \
	-d '{
		"jsonrpc": "2.0",
		"id": 1,
		"method": "initialize",
		"params": {
			"protocolVersion": "2025-03-26",
			"capabilities": {},
			"clientInfo": {"name": "quickstart", "version": "0.1.0"}
		}
	}'
```

Copy the `mcp-session-id` response header, then list tools:

```bash
curl -X POST "http://localhost:8000/mcp" \
	-H "accept: application/json, text/event-stream" \
	-H "Content-Type: application/json" \
	-H "mcp-session-id: <SESSION_ID>" \
	-d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

## Features

- REST API with full CRUD, search, filtering, pagination
- MCP server for AI agent integration
- Import from dbt MetricFlow YAML
- Export to JSON, YAML, OSI-compatible format, dbt
- Version history for every metric change
- Collections for organizing metrics by domain
- API key auth (optional)
- PostgreSQL with full-text search
- Single-process deployment (API + MCP from one service)

## API Documentation

OpenAPI docs:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

Useful examples:

Create a collection:

```bash
curl -X POST "http://localhost:8000/api/v1/collections" \
	-H "Content-Type: application/json" \
	-d '{"name":"finance","description":"Finance KPIs"}'
```

List metrics with search + filters:

```bash
curl "http://localhost:8000/api/v1/metrics?search=revenue&tags=finance&status=active&page=1&page_size=20"
```

Export catalog to YAML:

```bash
curl -X POST "http://localhost:8000/api/v1/metrics/export?format=yaml" -o metricstore_export.yaml
```

Import from dbt YAML:

```bash
curl -X POST "http://localhost:8000/api/v1/metrics/import?format=dbt" \
	-F "file=@metrics.yml"
```

## MCP Integration

MetricStore exposes MCP over HTTP at `/mcp`.

### Claude Desktop

If your MCP bridge/tooling supports streamable HTTP MCP endpoints, point it to:

- URL: `http://localhost:8000/mcp`

Example `claude_desktop_config.json` snippet (structure may vary by bridge version):

```json
{
	"mcpServers": {
		"metricstore": {
			"transport": "http",
			"url": "http://localhost:8000/mcp"
		}
	}
}
```

### Cursor / VS Code / Other MCP Clients

Use the same endpoint:

- `http://localhost:8000/mcp`

If auth is enabled, provide either:

- `X-API-Key` header
- `api_key` query parameter

### Built-in AI-optimized tools

Custom MCP-oriented tool routes include:

- `discover_metrics`
- `get_metric_definition`
- `search_metrics`
- `get_metric_sql`
- `list_collections`
- `get_collection_metrics`

## Import from dbt

MetricStore can ingest dbt MetricFlow YAML directly.

Example input (`metrics.yml`):

```yaml
semantic_models:
	- name: orders
		measures:
			- name: order_total
				agg: sum
				expr: amount
metrics:
	- name: revenue
		type: simple
		type_params:
			measure: order_total
```

Import command:

```bash
curl -X POST "http://localhost:8000/api/v1/metrics/import?format=dbt" \
	-F "file=@metrics.yml"
```

## Configuration

MetricStore reads settings from environment variables (and `.env`).

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://metricstore:metricstore@localhost:5432/metricstore` | Async SQLAlchemy database URL |
| `APP_NAME` | `MetricStore` | API title/name |
| `DEBUG` | `false` | Enables debug behavior |
| `API_PREFIX` | `/api/v1` | API router prefix |
| `AUTH_ENABLED` | `false` | Enable API-key authentication for API + MCP |
| `API_KEYS` | empty | Comma-separated API keys when auth is enabled |

## Deployment

### Railway

If you publish this repo as a template, you can add a one-click button:

```md
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/Trailblazer-Analytics/MetricStore)
```

Set required env vars in Railway:

- `DATABASE_URL`
- `AUTH_ENABLED`
- `API_KEYS` (if auth enabled)

### Fly.io (example)

```bash
fly launch
fly secrets set DATABASE_URL="postgresql+asyncpg://..."
fly deploy
```

### Docker Compose for production-like runs

Use:

```bash
docker compose up -d --build
```

For production, remove dev reload flags and pin image tags.

## Release Checklist

Use this checklist when shipping a new public release.

1. Ensure `main` is green:
	- CI passes (`test` + `lint`)
	- `ruff check .` and `pytest -q` pass locally (or known integration-test caveats are documented)
2. Merge the open "Release Please" PR (or wait for it to be created after merge commits land on `main`).
	- This updates version files and `CHANGELOG.md`.
3. Confirm a new Git tag (`vX.Y.Z`) is created.
	- Tag push triggers `.github/workflows/release.yml`.
4. Verify release artifacts:
	- GitHub Release entry is published
	- Docker image is available at `ghcr.io/trailblazer-analytics/metricstore:X.Y.Z`
	- Optional: PyPI publish job ran (when `PYPI_PUBLISH=true`)
5. Smoke test the release:
	- `docker pull ghcr.io/trailblazer-analytics/metricstore:X.Y.Z`
	- `docker compose up -d`
	- Open `http://localhost:8000/health` and `http://localhost:8000/docs`
6. Announce the release and link the changelog section.

## Contributing

See CONTRIBUTING.md for full setup and workflow.

Baseline expectations:

- Fork and open a PR from a feature branch
- Add/update tests for behavior changes
- Run lint + tests before opening PR
- Use Python 3.12+ and type hints for new code

## Roadmap

- [ ] Web UI (HTMX-based metric browser)
- [ ] Cube schema importer
- [ ] LookML importer
- [ ] Full OSI format support (tracking spec evolution)
- [ ] Webhook notifications on metric changes
- [ ] Metric lineage visualization
- [ ] Slack bot integration

## GitHub Repository Metadata Suggestions

Suggested description:

Open-source metrics catalog with REST API and MCP server. Define business metrics once, serve them to AI agents, BI tools, and applications.

Suggested topics:

- `metrics`
- `semantic-layer`
- `mcp`
- `model-context-protocol`
- `analytics`
- `dbt`
- `business-intelligence`
- `api`
- `metrics-catalog`
- `data-governance`
- `osid`

## License

Apache 2.0

---

MetricStore helps you standardize metric definitions without forcing a full platform rewrite.
