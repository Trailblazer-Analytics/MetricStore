# ── Stage 1: dependency installer ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

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
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /usr/local /usr/local

# Copy application source
COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.metricstore.main:app", "--host", "0.0.0.0", "--port", "8000"]
