#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must point to a disposable test database}"
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini current
