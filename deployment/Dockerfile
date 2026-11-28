# Multi-stage offline-ready Dockerfile for TRSQL Backend API (Python 3.12).
# Build from repository root:
#   docker build -f deployment/Dockerfile -t trsql-api:local .
# Air-gapped wheelhouse build:
#   docker build -f deployment/Dockerfile --build-arg PIP_NO_INDEX=1 --build-arg PIP_FIND_LINKS=/wheels -t trsql-api:local .

FROM python:3.12-slim AS builder

ARG PIP_NO_INDEX=0
ARG PIP_FIND_LINKS=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY backend ./backend

# Install backend + FastAPI runtime dependencies (supports offline wheelhouse via PIP_NO_INDEX=1).
RUN pip install --no-cache-dir --upgrade pip setuptools wheel || true
RUN if [ "$PIP_NO_INDEX" = "1" ] && [ -n "$PIP_FIND_LINKS" ] && [ -d "$PIP_FIND_LINKS" ]; then \
      pip install --no-cache-dir --no-index --find-links="$PIP_FIND_LINKS" ".[api]"; \
    else \
      pip install --no-cache-dir ".[api]"; \
    fi


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TRSQL_OFFLINE="1" \
    HF_HUB_OFFLINE="1" \
    TRANSFORMERS_OFFLINE="1" \
    TRSQL_MODEL_DIR="/app/models" \
    TRSQL_AUDIT_LOG_DIR="/app/logs" \
    TRSQL_LOG_RETENTION_DAYS="180" \
    TRSQL_ASGI_APP="backend.api.app:create_default_app"

RUN groupadd --system --gid 10001 trsql \
    && useradd --system --uid 10001 --gid trsql --create-home --home-dir /app trsql \
    && mkdir -p /app/models /app/logs /app/configs /app/security_policies /app/deployment \
    && chown -R trsql:trsql /app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=trsql:trsql backend ./backend
COPY --chown=trsql:trsql configs ./configs
COPY --chown=trsql:trsql security_policies ./security_policies
COPY --chown=trsql:trsql deployment/verify_models.py ./deployment/verify_models.py
COPY --chown=trsql:trsql models/*.md ./models/

USER trsql

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# Verify mounted models (reject .bin/pickle and check SHA-256 when manifest is present), then start API.
CMD ["sh", "-c", "python deployment/verify_models.py --models-dir \"${TRSQL_MODEL_DIR:-/app/models}\" --allow-empty && exec uvicorn \"${TRSQL_ASGI_APP}\" --factory --host 0.0.0.0 --port 8000"]
