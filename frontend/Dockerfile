# syntax=docker/dockerfile:1.7
FROM node:24.18.0-bookworm-slim AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM dependencies AS build
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_OIDC_AUTHORITY=
ARG NEXT_PUBLIC_OIDC_CLIENT_ID=
ARG NEXT_PUBLIC_OIDC_SCOPE="openid profile email agent:run"
ARG NEXT_PUBLIC_DEFAULT_WORKSPACE_ID=
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_OIDC_AUTHORITY=${NEXT_PUBLIC_OIDC_AUTHORITY} \
    NEXT_PUBLIC_OIDC_CLIENT_ID=${NEXT_PUBLIC_OIDC_CLIENT_ID} \
    NEXT_PUBLIC_OIDC_SCOPE=${NEXT_PUBLIC_OIDC_SCOPE} \
    NEXT_PUBLIC_DEFAULT_WORKSPACE_ID=${NEXT_PUBLIC_DEFAULT_WORKSPACE_ID}
COPY frontend/ ./
RUN npm run build && rm -rf .next/cache

FROM dependencies AS production-dependencies
RUN npm prune --omit=dev

FROM node:24.18.0-bookworm-slim AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
RUN groupadd --system --gid 10001 nextjs && useradd --system --uid 10001 --gid nextjs --create-home --shell /usr/sbin/nologin nextjs
COPY --from=production-dependencies --chown=nextjs:nextjs /app/node_modules ./node_modules
COPY --from=build --chown=nextjs:nextjs /app/.next ./.next
COPY --from=build --chown=nextjs:nextjs /app/package.json ./package.json
USER nextjs
EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
