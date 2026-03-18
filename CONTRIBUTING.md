# Contributing to MetricStore

Thanks for contributing to MetricStore.

## Development Setup

### Prerequisites

- Python 3.12+
- Docker + Docker Compose
- Git

### 1) Clone and create virtual environment

```bash
git clone https://github.com/<your-user>/MetricStore.git
cd MetricStore
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```bash
pip install -e .[dev]
```

### 3) Start Postgres + app (optional, quickest path)

```bash
docker compose up -d --build
```

### 4) Run tests and lint

```bash
pytest -q
ruff check .
ruff format --check .
```

## Project Standards

- Python 3.12+
- Type hints for all new public functions/classes
- Keep modules focused and small
- Prefer explicit, readable logic over clever one-liners
- Add or update tests for all behavior changes
- Keep API responses backward-compatible unless explicitly planned

## Testing Guidelines

- Unit tests should be fast and isolated
- Integration tests should validate API behavior against Postgres
- Use realistic metric examples in fixtures
- Cover failure paths (validation, auth, not found, conflicts)

## Branch and PR Workflow

1. Fork the repository
2. Create a branch from `main`:
   - `feat/<short-name>` for features
   - `fix/<short-name>` for fixes
3. Make focused commits with clear messages
4. Run lint + tests locally
5. Open a Pull Request

## Pull Request Checklist

- [ ] Tests added/updated for the change
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] `pytest -q` passes (or failures explained)
- [ ] Docs updated for API/config behavior changes

## Commit Message Style

Use imperative style and include scope when helpful.

Examples:

- `feat(api): add dbt import upsert behavior`
- `fix(auth): enforce API key for MCP routes`
- `test(metrics): add integration coverage for export formats`

## Reporting Security Issues

Do not open public issues for sensitive vulnerabilities.
Create a private report to maintainers with:

- Affected version/commit
- Reproduction steps
- Impact assessment
- Suggested fix (if available)
