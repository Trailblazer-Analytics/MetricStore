# syntax=docker/dockerfile:1
# ── Stage 1: dependency installer ─────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy packaging metadata only — avoids full source invalidating the layer
COPY pyproject.toml README.md ./

# Hatchling needs the package present to resolve the version during install.
# We create a minimal stub so `pip install .` succeeds before copying real src.
RUN mkdir -p src/metricstore \
    && echo '__version__ = "0.1.0"' > src/metricstore/__init__.py

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# ── Stage 2: production runtime ───────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ARG VERSION=dev
ARG GIT_SHA=unknown

LABEL org.opencontainers.image.title="MetricStore" \
      org.opencontainers.image.description="Governed business metrics catalog with REST API and MCP server" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.source="https://github.com/YOUR_USERNAME/metricstore" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.base.name="python:3.12-slim"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /usr/local /usr/local

# Copy application source
COPY src/ ./src/

# Non-root user for security
RUN addgroup --system metricstore && adduser --system --ingroup metricstore metricstore
USER metricstore

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "src.metricstore.main:app", "--host", "0.0.0.0", "--port", "8000"]
