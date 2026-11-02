# Cody webhook service. Build context is the repo root (infra/docker-compose.yml: context ..).
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM python:3.12.13-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY agent ./agent
COPY config ./config
COPY db ./db
COPY scripts ./scripts
USER nobody
EXPOSE 8080
CMD ["/app/.venv/bin/uvicorn", "agent.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
