# Local Development Auth Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local `/agent-runs` page create and follow development-only research tasks without weakening production OIDC authentication.

**Architecture:** A small frontend auth-runtime module converts explicit public configuration into either OIDC or development request headers. `AuthProvider` owns mode selection and exposes validated headers; `AgentRunPanel` consumes those headers uniformly for create/read/SSE/cancel. Docker development config opts into development mode, while production remains explicitly OIDC and the backend production rejection of development headers is unchanged.

**Tech Stack:** Next.js 15, React 19, TypeScript, oidc-client-ts, Vitest, Testing Library, FastAPI, Docker Compose.

## Global Constraints

- Only `NEXT_PUBLIC_AUTH_MODE=development` may produce development identity headers.
- Unknown modes and missing/blank identity values fail closed as `configuration_error`.
- Production backend authentication code in `backend/app/api/v1/agent_runs.py` must not change.
- OIDC mode continues to send only `Authorization` and `X-Workspace-ID`.
- Development mode sends only `X-Development-Principal-ID` and `X-Development-Workspace-ID`.
- The UI must label development mode and must not claim real market-data or model execution.
- Do not modify or stage `.superpowers/`.

---

### Task 1: Auth runtime and provider

**Files:**
- Create: `frontend/lib/auth/runtime.ts`
- Create: `frontend/tests/auth-runtime.test.ts`
- Modify: `frontend/components/auth-provider.tsx`
- Modify: `frontend/tests/auth-provider.test.tsx`

**Interfaces:**
- Consumes: existing `readPublicOidcConfig(environment)` and `UserManager` OIDC flow.
- Produces: `AuthMode`, `readAuthMode(environment, nodeEnvironment)`, `buildDevelopmentHeaders(principalId, workspaceId)`, and `AuthContextValue.requestHeaders`.

- [ ] **Step 1: Write failing auth-runtime tests**

Create `frontend/tests/auth-runtime.test.ts` with literal expectations:

```ts
import { describe, expect, it } from "vitest";

import { buildDevelopmentHeaders, readAuthMode } from "../lib/auth/runtime";

describe("auth runtime", () => {
  it("defaults next dev to development and production builds to oidc", () => {
    expect(readAuthMode({}, "development")).toBe("development");
    expect(readAuthMode({}, "production")).toBe("oidc");
  });

  it("rejects an unknown explicit auth mode", () => {
    expect(() => readAuthMode({ NEXT_PUBLIC_AUTH_MODE: "unsafe" }, "development"))
      .toThrow("Unsupported public auth mode");
  });

  it("builds only explicit development identity headers", () => {
    expect(buildDevelopmentHeaders("local-user", "local-workspace")).toEqual({
      "X-Development-Principal-ID": "local-user",
      "X-Development-Workspace-ID": "local-workspace",
    });
    expect(() => buildDevelopmentHeaders("   ", "local-workspace"))
      .toThrow("Development identity configuration is incomplete");
  });
});
```

- [ ] **Step 2: Run the new unit test and confirm RED**

Run `npm --prefix frontend test -- --run tests/auth-runtime.test.ts`.

Expected: FAIL because `frontend/lib/auth/runtime.ts` does not exist.

- [ ] **Step 3: Implement the minimal auth runtime**

Create `frontend/lib/auth/runtime.ts`:

```ts
export type AuthMode = "oidc" | "development";
type PublicEnvironment = Record<string, string | undefined>;

export function readAuthMode(
  environment: PublicEnvironment,
  nodeEnvironment: string | undefined,
): AuthMode {
  const configured = environment.NEXT_PUBLIC_AUTH_MODE?.trim();
  if (!configured) return nodeEnvironment === "development" ? "development" : "oidc";
  if (configured !== "oidc" && configured !== "development") {
    throw new Error("Unsupported public auth mode");
  }
  return configured;
}

export function buildDevelopmentHeaders(
  principalId: string | undefined,
  workspaceId: string | undefined,
): Record<string, string> {
  const principal = principalId?.trim();
  const workspace = workspaceId?.trim();
  if (!principal || !workspace) {
    throw new Error("Development identity configuration is incomplete");
  }
  return {
    "X-Development-Principal-ID": principal,
    "X-Development-Workspace-ID": workspace,
  };
}
```

- [ ] **Step 4: Run auth-runtime tests and confirm GREEN**

Run the Step 2 command. Expected: 3 tests pass.

- [ ] **Step 5: Write failing AuthProvider development-mode test**

Extend the test probe to render `status`, `mode`, and serialized `requestHeaders`, then add:

```tsx
it("authenticates an explicitly configured development identity", async () => {
  render(
    <AuthProvider environment={{
      NEXT_PUBLIC_AUTH_MODE: "development",
      NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID: "local-user",
      NEXT_PUBLIC_DEFAULT_WORKSPACE_ID: "local-workspace",
    }}>
      <AuthState />
    </AuthProvider>,
  );

  expect(await screen.findByText("authenticated|development")).toBeInTheDocument();
  expect(screen.getByText(/X-Development-Principal-ID/)).toHaveTextContent("local-user");
});
```

Keep the existing empty-environment test, but pass `NEXT_PUBLIC_AUTH_MODE: "oidc"` so it proves OIDC never silently downgrades.

- [ ] **Step 6: Run AuthProvider test and confirm RED**

Run `npm --prefix frontend test -- --run tests/auth-provider.test.tsx`.

Expected: FAIL because the provider does not expose mode/request headers and still initializes OIDC.

- [ ] **Step 7: Implement provider mode selection**

Update the public environment with `NEXT_PUBLIC_AUTH_MODE` and `NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID`. Export `AuthContextValue`, add:

```ts
mode: AuthMode | null;
requestHeaders: Record<string, string> | null;
```

At the start of the existing effect, call `readAuthMode(environment, process.env.NODE_ENV)`. For `development`, call `buildDevelopmentHeaders(...)`, set workspace, mode, request headers, `authenticated`, and return without constructing `UserManager`. For `oidc`, keep the existing flow and set request headers with `buildAuthenticatedHeaders(user.access_token, configuredWorkspaceId)` only when a token exists. Configuration exceptions continue to set `configuration_error`.

- [ ] **Step 8: Run Task 1 tests and typecheck**

```bash
npm --prefix frontend test -- --run tests/auth-runtime.test.ts tests/auth-provider.test.tsx tests/oidc.test.ts
npm --prefix frontend run typecheck
```

Expected: all selected tests and typecheck pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add frontend/lib/auth/runtime.ts frontend/components/auth-provider.tsx frontend/tests/auth-runtime.test.ts frontend/tests/auth-provider.test.tsx
git commit -m "feat(auth): add explicit local development mode"
```

### Task 2: Agent Run panel consumes validated headers

**Files:**
- Modify: `frontend/components/agent-run-panel.tsx`
- Modify: `frontend/tests/agent-run-auth.test.tsx`
- Modify: `frontend/tests/agent-run-panel.test.tsx`

**Interfaces:**
- Consumes: `useAuth()` with `status`, `mode`, `requestHeaders`, `error`, `signIn`, and `signOut` from Task 1.
- Produces: one request-header path shared by restore, create, SSE, and cancel; a visible development-mode notice.

- [ ] **Step 1: Replace the auth mock with development headers and write the failing request test**

In `frontend/tests/agent-run-auth.test.tsx`, make `useAuth()` return:

```ts
{
  status: "authenticated",
  mode: "development",
  requestHeaders: {
    "X-Development-Principal-ID": "local-user",
    "X-Development-Workspace-ID": "local-workspace",
  },
  error: null,
  signIn: vi.fn(),
  signOut: vi.fn(),
}
```

Rename the test and assert the first POST contains those two headers and contains neither `Authorization` nor `X-Workspace-ID`.

- [ ] **Step 2: Run the authentication test and confirm RED**

Run `npm --prefix frontend test -- --run tests/agent-run-auth.test.tsx`.

Expected: FAIL because `AgentRunPanel` still reads `accessToken` and does not call fetch.

- [ ] **Step 3: Update AgentRunPanel to use provider headers**

Remove the direct `buildAuthenticatedHeaders` import. Replace every `accessToken/workspaceId` guard with `auth.requestHeaders`, and pass that object to `readRun`, create POST, SSE, and cancel. Change the effect dependency to `[auth.requestHeaders]`.

Render this notice only in development mode:

```tsx
{auth.mode === "development" && (
  <p className="development-mode-notice">本地开发身份模式：任务不会调用真实行情或生产模型。</p>
)}
```

Show login/logout buttons only for `mode === "oidc"`.

- [ ] **Step 4: Update the existing panel auth mocks**

In `frontend/tests/agent-run-panel.test.tsx`, return an OIDC-shaped `requestHeaders` literal and `mode: "oidc"`. Do not reconstruct headers through the production helper.

- [ ] **Step 5: Run Task 2 tests and confirm GREEN**

Run `npm --prefix frontend test -- --run tests/agent-run-auth.test.tsx tests/agent-run-panel.test.tsx`.

Expected: all Agent Run panel tests pass, including creation, restoration, SSE, and cancellation.

- [ ] **Step 6: Commit Task 2**

```bash
git add frontend/components/agent-run-panel.tsx frontend/tests/agent-run-auth.test.tsx frontend/tests/agent-run-panel.test.tsx
git commit -m "fix(agent-runs): connect local development identity"
```

### Task 3: Development environment, documentation, and acceptance

**Files:**
- Modify: `frontend/Dockerfile`
- Modify: `deploy/compose.base.yml`
- Modify: `deploy/env/development.example`
- Modify: `deploy/env/production.example`
- Modify: `docs/development/local-setup.md`

**Interfaces:**
- Consumes: the public auth variables defined in Task 1.
- Produces: reproducible Docker/local startup configuration and an operator-visible acceptance path.

- [ ] **Step 1: Add frontend build arguments**

Add these Docker build arguments and exported environment values alongside the existing OIDC arguments:

```dockerfile
ARG NEXT_PUBLIC_AUTH_MODE=oidc
ARG NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID=
ARG NEXT_PUBLIC_DEFAULT_WORKSPACE_ID=
```

- [ ] **Step 2: Pass auth arguments through Compose**

Add to `frontend.build.args`:

```yaml
NEXT_PUBLIC_AUTH_MODE: ${NEXT_PUBLIC_AUTH_MODE:-oidc}
NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID: ${NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID:-}
NEXT_PUBLIC_DEFAULT_WORKSPACE_ID: ${NEXT_PUBLIC_DEFAULT_WORKSPACE_ID:-}
```

- [ ] **Step 3: Make environment examples explicit**

Append to `deploy/env/development.example`:

```dotenv
NEXT_PUBLIC_AUTH_MODE=development
NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID=local-user
NEXT_PUBLIC_DEFAULT_WORKSPACE_ID=local-workspace
```

Add `NEXT_PUBLIC_AUTH_MODE=oidc` to `deploy/env/production.example`. Do not add development identity values to the production example.

- [ ] **Step 4: Document direct and Docker startup**

Update `docs/development/local-setup.md` with the direct command:

```bash
NEXT_PUBLIC_AUTH_MODE=development \
NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID=local-user \
NEXT_PUBLIC_DEFAULT_WORKSPACE_ID=local-workspace \
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 \
npm --prefix frontend run dev
```

State that the standard origin is `http://localhost:3000`; when using 3001, the API must start with `CORS_ORIGINS=http://localhost:3000,http://localhost:3001`.

- [ ] **Step 5: Run full automated verification**

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run
npm --prefix frontend run build
uv --cache-dir /private/tmp/p4-uv-cache run ruff check .
uv --cache-dir /private/tmp/p4-uv-cache run mypy backend/app legacy/scoring.py
uv --cache-dir /private/tmp/p4-uv-cache run pytest -q
docker compose --env-file deploy/env/development.example -f deploy/compose.base.yml -f deploy/compose.dev.yml config -q
git diff --check
```

Expected: all commands exit 0. Backend test output may retain the existing Starlette/httpx deprecation warning; do not report it as a new failure.

- [ ] **Step 6: Restart the local frontend with explicit development settings**

Stop the temporary 3001 Next.js process, then start it with the documented variables. Because the existing API permits only 3000, either use the rebuilt Docker frontend on 3000 or restart the development API with 3001 included in `CORS_ORIGINS`; do not disable CORS.

- [ ] **Step 7: Perform browser acceptance**

Open `/agent-runs`, verify the development-mode notice is visible and no OIDC configuration error is shown. Enter `贵州茅台的股价走势`, click `启动研究`, and verify the authoritative UI signals are `状态：completed` and the persisted event text. Record that the output is the deterministic development baseline, not real market research.

- [ ] **Step 8: Commit Task 3**

```bash
git add frontend/Dockerfile deploy/compose.base.yml deploy/env/development.example deploy/env/production.example docs/development/local-setup.md
git commit -m "docs(dev): enable local research task workflow"
```
