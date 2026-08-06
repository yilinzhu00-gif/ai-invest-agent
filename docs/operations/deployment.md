# Provider-neutral deployment contract

This repository does not configure a cloud account. A human operator must bind GitHub OIDC, staging host, Secret Manager and production Environment approval before deployment. CI builds immutable commit-SHA images; migrations run as a separate job; smoke tests target only an explicitly supplied test URL.

Copy `deploy/env/provider-binding.example` to an operator-controlled, untracked binding file and replace every placeholder with provider-owned values. Validate it without exposing secrets:

```bash
./scripts/validate-provider-binding.sh /secure/path/provider-binding.env
```

The contract requires a cloud Provider/region, immutable image digest, GitHub OIDC audience, application OIDC/JWK URLs, secret-manager references for database and object storage, an isolated object bucket, and Grafana URL. It deliberately contains secret references rather than credentials and does not create cloud resources.
