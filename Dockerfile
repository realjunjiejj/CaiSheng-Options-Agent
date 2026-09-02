# syntax=docker/dockerfile:1
# CaiSheng (Options Alpha) — Reproducible Google Cloud Run container

FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217 AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Pin the build tool and install the exact locked dependency graph.
COPY --from=ghcr.io/astral-sh/uv:0.9.26@sha256:9a23023be68b2ed09750ae636228e903a54a05ea56ed03a934d00fe9fbeded4b /uv /bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217 AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY app.py cli.py README.md ./
COPY data/ ./data/
COPY config/ ./config/
COPY docs/ ./docs/
COPY scripts/ ./scripts/

# Cloud Run service state is deliberately non-authoritative and ephemeral.
# The SQLite execution ledger runs only on the persistent execution host.
RUN mkdir -p /tmp/caisheng /app/.streamlit && \
    useradd -m -u 10001 caisheng && \
    chown -R caisheng:caisheng /app /tmp/caisheng

ENV PYTHONUNBUFFERED=1 \
    PROJECT_ROOT=/app \
    PORT=8080 \
    VOLAGENT_LEDGER_DB_PATH=/tmp/caisheng/non_authoritative_ledger.db \
    VOLAGENT_ALLOW_ORDER_SUBMISSION=false \
    VOLAGENT_ALPACA_PAPER_TRADE=true \
    STREAMLIT_SERVER_PORT=8080 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

USER caisheng

# Cloud Run routes one ingress port. UI and MCP are separate services built
# from this image, and each service listens on PORT.
EXPOSE 8080

STOPSIGNAL SIGTERM

ENTRYPOINT ["/bin/bash", "/app/scripts/cloud_run_entrypoint.sh"]
CMD ["streamlit"]
