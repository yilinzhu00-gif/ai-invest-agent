# Container boundary

The root `docker-compose.yml` is the supported local entry point. It includes
the versioned service definitions under `deploy/compose.base.yml` and
`deploy/compose.dev.yml`; production overlays remain under `deploy/` so the
existing deployment and rollback runbooks keep their paths.

The `backend` image runs FastAPI and Celery, `postgres` stores relational
research data, `vector-db` is an isolated pgvector boundary, and `redis`
provides queue/cache primitives. The current application schema still uses
PostgreSQL/pgvector for durable retrieval; `VECTOR_DB_URL` makes the separate
vector service an explicit, deployable boundary without pretending that a
provider migration has already been completed.

The backend service exposes the compatibility network alias `api`, so existing
Nginx and operator commands continue to work while new deployments use the
clearer `backend` name.
