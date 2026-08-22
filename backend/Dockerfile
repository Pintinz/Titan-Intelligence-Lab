# TitanIQ backend — production image. No Dockerfile existed anywhere in the repo before this
# (Production Readiness Audit §9); the app previously only ran as a bare local `uvicorn` process.
# Multi-stage: the builder installs the package and its (heavy — lightgbm/xgboost/catboost/shap)
# ML dependencies into an isolated venv; the runtime stage ships only that venv plus source, no
# compilers, on a non-root user.

# ---- Build stage -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# build-essential is only needed here (compiling any dependency without a prebuilt wheel for the
# target platform) — the runtime stage below never installs it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# ---- Runtime stage ----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# lightgbm/xgboost/catboost link against libgomp (OpenMP) at import time, not just at build time
# — omitting this makes every prediction request needing one of those model families crash.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin titaniq

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=titaniq:titaniq . .

USER titaniq

EXPOSE 8000

# Deliberately the lightweight liveness endpoint, not /api/v1/health/ready — a DB/Redis outage
# must not make Docker/Render conclude this process itself is dead and start cycling it; that's
# what the separate readiness endpoint is for (apps/api/main.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# --workers closes the "no documented multi-worker production invocation" gap (Production
# Readiness Audit §9 — the app previously only ever ran as a single bare `uvicorn` process, no
# `--workers`, no process manager). Override WEB_CONCURRENCY per deploy target's CPU budget.
#
# `alembic upgrade head &&` — found live (2026-08-23): the actual deployed Render web service was
# created manually (outside the render.yaml Blueprint, which does specify this via its own
# dockerCommand), and neither a Docker Command override nor a Pre-Deploy Command was ever
# configured on it — meaning no migration had ever run automatically on any deploy of this
# service. Every prior schema change only ever took effect because it was applied by a manual
# one-off script against production, never as a real part of the deploy process itself. Putting
# it in the image's own default CMD (rather than depending on a per-service dashboard field that's
# easy to forget, exactly as happened here) means every deploy of this service is correct by
# construction, not by remembering to configure something outside the repo. `alembic upgrade
# head` is a no-op when already current, so this is always safe to run on every start.
#
# This one image also runs the Celery worker and Beat scheduler — those override this CMD entirely
# at deploy time (their own Docker Command field on Render), so they never inherit the migration
# step below and never race each other applying it:
#   docker run <image> celery -A apps.worker.bootstrap worker --loglevel=info
#   docker run <image> celery -A apps.worker.bootstrap beat --loglevel=info
CMD ["sh", "-c", "alembic upgrade head && uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-4}"]
