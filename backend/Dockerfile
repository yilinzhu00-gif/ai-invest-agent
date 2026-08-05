# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.8.15 AS uv

FROM python:3.12.11-slim-bookworm AS dependencies
COPY --from=uv /uv /uvx /bin/
WORKDIR /build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12.11-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/logs && chown app:app /app/logs
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=app:app scoring.py agent.py app.py finance.py llm.py rag.py ./
COPY --chown=app:app backend/__init__.py ./backend/__init__.py
COPY --chown=app:app backend/app ./backend/app
COPY --chown=app:app backend/alembic ./backend/alembic
COPY --chown=app:app backend/alembic.ini ./backend/alembic.ini
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
