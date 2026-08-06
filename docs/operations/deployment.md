# Provider-neutral deployment contract

This repository does not configure a cloud account. A human operator must bind GitHub OIDC, staging host, Secret Manager and production Environment approval before deployment. CI builds immutable commit-SHA images; migrations run as a separate job; smoke tests target only an explicitly supplied test URL.
