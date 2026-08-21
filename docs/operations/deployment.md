# Provider-neutral deployment contract

This repository does not configure a cloud account. A human operator must bind GitHub OIDC, staging host, Secret Manager and production Environment approval before deployment. CI builds immutable commit-SHA images; migrations run as a separate job; smoke tests target only an explicitly supplied test URL.

Copy `deploy/env/provider-binding.example` to an operator-controlled, untracked binding file and replace every placeholder with provider-owned values. Validate it without exposing secrets:

```bash
./scripts/validate-provider-binding.sh /secure/path/provider-binding.env
```

The contract requires a cloud Provider/region, immutable image digest, GitHub OIDC audience, application OIDC/JWK URLs, secret-manager references for database and object storage, an isolated object bucket, and Grafana URL. It deliberately contains secret references rather than credentials and does not create cloud resources.

## Alibaba Cloud single-ECS profile

This profile is for the existing 2 GiB ECS host at `aiinvestmentagent.cn`. It is a real authenticated application deployment, but is intentionally **not** a high-availability architecture: PostgreSQL, Redis, the worker and the application share one host. RDS PostgreSQL, OSS, Prometheus and Grafana are excluded to limit cost and memory use. Do not describe this profile as multi-AZ, managed-backup or object-storage-isolated production.

Only Nginx publishes ports 80 and 443. Never add ECS security-group rules for 3000, 5432, 6379, 8000 or 3001.

### 1. Configure Alibaba Cloud IDaaS

In IDaaS EIAM, create a self-developed **public SPA** application using OpenID Connect Authorization Code with PKCE. Do not create or place a client secret in the Next.js application.

Set these URLs exactly:

```text
Login redirect URI: https://aiinvestmentagent.cn/oidc/callback
Logout callback URI: https://aiinvestmentagent.cn/
```

Create a user, grant that user an API scope named `agent:run`, and record the user subject (`sub`) shown by IDaaS. From the application's OpenID Connect discovery document, record the issuer and `jwks_uri`. Record the public client ID and the API audience configured by IDaaS. The API refuses tokens with a different issuer, audience, scope, expiration or token type.

### 2. Prepare the host and secrets

On the ECS host, use the `docker-compose` command because this host currently has Compose 1.29:

```bash
sudo mkdir -p /opt/investment-agent/certs
sudo chown -R "$USER" /opt/investment-agent
git clone <your-repository-ssh-or-https-url> /opt/investment-agent/app
cd /opt/investment-agent/app
cp deploy/env/single-node.example /opt/investment-agent/.env
openssl rand -hex 32
```

Put the final generated hexadecimal value in both `POSTGRES_PASSWORD` and the password section of `DATABASE_URL`. Hexadecimal values are URL-safe. Fill every `replace-with-...` value in `/opt/investment-agent/.env`; do not copy that file back into Git.

Download the already-issued Alibaba Cloud certificate in **Nginx** format. Upload the certificate PEM and private KEY only to the host, then set restrictive permissions:

```bash
chmod 700 /opt/investment-agent/certs
chmod 600 /opt/investment-agent/certs/aiinvestmentagent.cn.key
chmod 644 /opt/investment-agent/certs/aiinvestmentagent.cn.pem
```

Their exact absolute paths must match `TLS_CERT_FILE` and `TLS_KEY_FILE` in `/opt/investment-agent/.env`.

### 3. Start and bootstrap membership

Validate Compose before creating containers:

```bash
cd /opt/investment-agent/app
docker-compose --env-file /opt/investment-agent/.env \
  -f deploy/compose.base.yml -f deploy/compose.single-node.yml config --quiet
```

Build and start the services:

```bash
docker-compose --env-file /opt/investment-agent/.env \
  -f deploy/compose.base.yml -f deploy/compose.single-node.yml up -d --build
docker-compose --env-file /opt/investment-agent/.env \
  -f deploy/compose.base.yml -f deploy/compose.single-node.yml ps
```

The first membership is a deliberate operator action. Replace the two values with the IDaaS user `sub` and the workspace ID from `NEXT_PUBLIC_DEFAULT_WORKSPACE_ID`:

```bash
docker-compose --env-file /opt/investment-agent/.env \
  -f deploy/compose.base.yml -f deploy/compose.single-node.yml \
  run --rm \
  -e BOOTSTRAP_WORKSPACE_ID='<workspace-id>' \
  -e BOOTSTRAP_USER_ID='<idaas-user-sub>' \
  -e BOOTSTRAP_WORKSPACE_ROLE='owner' \
  backend python -m backend.app.operations.bootstrap_workspace
```

The command is idempotent: it creates a missing membership and will not overwrite an existing one.

### 4. Verify, update and roll back

Verify only through HTTPS and Nginx:

```bash
./scripts/verify-single-node-deployment.sh https://aiinvestmentagent.cn
curl -I https://aiinvestmentagent.cn
```

Expected: `/api/v1/health/ready` succeeds and the root response contains `Strict-Transport-Security`. Then sign in through IDaaS, visit `/agent-runs`, and create a task. Verify `docker-compose ... ps` shows `backend`, `frontend`, `worker`, `redis`, `postgres`, `vector-db` and `nginx` running; `migrate` exits successfully. The backend still publishes the internal `api` network alias for older operator configuration.

For an update, first fetch a reviewed commit, then rebuild:

```bash
git fetch origin
git checkout <reviewed-commit-sha>
docker-compose --env-file /opt/investment-agent/.env \
  -f deploy/compose.base.yml -f deploy/compose.single-node.yml up -d --build
```

For a code rollback, check out the previous reviewed commit and run the same command. Do not run `docker-compose down -v`, delete named volumes, or automatically downgrade Alembic migrations.
