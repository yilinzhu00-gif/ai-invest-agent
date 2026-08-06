# Alibaba Cloud OIDC Single-Node Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the application securely on one Alibaba Cloud ECS host with HTTPS, OIDC login, Bearer-token API calls, durable local PostgreSQL/Redis/Celery services, and no publicly exposed internal ports.

**Architecture:** Alibaba Cloud IDaaS performs OIDC Authorization Code + PKCE. The browser retains only the short-lived access token in memory and attaches it plus the selected workspace to protected calls. Nginx is the sole public entrypoint and proxies `/api/` to FastAPI; the application network contains PostgreSQL, Redis, Celery, migration, API, and frontend services.

**Tech Stack:** Next.js 15, React 19, `oidc-client-ts`, FastAPI, PyJWT/JWKS, Celery, Redis, PostgreSQL 16, Docker Compose 1.29-compatible syntax, Nginx.

## Global Constraints

- `APP_ENV=production` requires an explicit OIDC issuer, audience and JWKS URL.
- The browser uses Authorization Code + PKCE and must never contain an OIDC client secret.
- Protected API calls contain `Authorization: Bearer <access-token>` and `X-Workspace-ID`; development identity headers are not sent in production.
- PostgreSQL, Redis, API, frontend and Grafana ports must not be published to the host.
- TLS key files and populated environment files remain ignored and operator controlled.
- The target host has 2 GiB RAM; Prometheus and Grafana are excluded from the single-node profile.

---

### Task 1: Browser authentication boundary

**Files:**
- Create: `frontend/lib/auth/oidc.ts`
- Create: `frontend/components/auth-provider.tsx`
- Create: `frontend/tests/oidc.test.ts`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/components/agent-run-panel.tsx`
- Modify: `frontend/package.json`

**Interfaces:**
- Produces `AuthProvider`, `useAuth()`, and `buildAuthenticatedHeaders(token, workspaceId)`.
- Consumes public `NEXT_PUBLIC_OIDC_*` settings only.

- [ ] Write unit tests that prove authenticated headers contain a Bearer token and never contain development headers.
- [ ] Run `npm test -- --run tests/oidc.test.ts` and verify the missing module fails.
- [ ] Add the minimal OIDC PKCE provider, login/logout UI, and request header helper.
- [ ] Convert Agent Run calls to the authenticated helper and display a login/workspace-required state.
- [ ] Run frontend lint, typecheck and tests.

### Task 2: OIDC token acceptance and workspace bootstrap

**Files:**
- Create: `backend/app/operations/bootstrap_workspace.py`
- Create: `backend/tests/unit/test_workspace_bootstrap.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/security/authentication.py`
- Modify: `backend/tests/security/test_auth_api.py`

**Interfaces:**
- Produces `bootstrap_workspace(database_url, workspace_id, user_id)` and an operator CLI.
- Accepts only configured access-token `typ` values and still requires issuer, audience, expiration, nonce-time claims and scope.

- [ ] Write failing tests for idempotent workspace bootstrap and accepted access token types.
- [ ] Run targeted pytest and verify expected failures.
- [ ] Implement the smallest idempotent bootstrap command and configurable access-token type allowlist.
- [ ] Run security/unit tests and static checks.

### Task 3: Single-node HTTPS deployment contract

**Files:**
- Create: `deploy/compose.single-node.yml`
- Create: `deploy/nginx/default.conf.template`
- Create: `deploy/env/single-node.example`
- Create: `scripts/verify-single-node-deployment.sh`
- Create: `backend/tests/unit/test_single_node_deployment.py`
- Modify: `.gitignore`
- Modify: `deploy/compose.base.yml`
- Modify: `docs/operations/deployment.md`

**Interfaces:**
- `docker-compose --env-file /opt/investment-agent/.env -f deploy/compose.base.yml -f deploy/compose.single-node.yml up -d --build` exposes only 80 and 443.
- `scripts/verify-single-node-deployment.sh` refuses a non-HTTPS target and checks public health through Nginx.

- [ ] Write a static deployment contract test for no internal host ports, TLS files and Nginx SSE proxy settings.
- [ ] Run the test to establish the red failure.
- [ ] Add Compose, Nginx and environment templates without credentials.
- [ ] Add a guarded verification script and exact ECS install/update/rollback instructions.
- [ ] Run deployment contract tests and shell syntax checks.

### Task 4: Full local verification and operator handoff

**Files:**
- Modify: `README.md`
- Modify: `docs/operations/deployment.md`

- [ ] Run backend tests, frontend lint/typecheck/tests/build, deployment static checks, and `docker-compose config` with a disposable env file.
- [ ] Record the exact Alibaba Cloud IDaaS fields: issuer, discovery/JWKS URL, public client ID, redirect/logout URLs, audience, `agent:run` scope, user subject, workspace ID.
- [ ] Document certificate placement, first deployment, membership bootstrap, HTTPS smoke checks, update and rollback commands.
- [ ] Commit only source, templates and documentation; never secrets, certificates or cloud credentials.
