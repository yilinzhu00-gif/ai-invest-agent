# P2-03 Typed Tool Registry Implementation Plan

**Goal:** Provide a fixed, typed, read-only tool registry with authorization, input validation, bounded invocation counts, timeout, and safe audit metadata.

**Architecture:** A `ToolDefinition` holds Pydantic input/output models and static policy metadata. `ToolRegistry.invoke` validates the named whitelist and input before `ToolPolicy` checks principal/workspace/permission/access/count; handlers receive validated models only. The four first-party tools are fixed at application construction, and no registration API exists.

**Files:** Create `backend/app/tools/{base,policy,registry,market_snapshot,score_stock,search_knowledge,query_table}.py`; create unit/security tests; document no-shell/no-network boundary.

**TDD steps:** Write a failing unknown/unauthorized/schema test; run it; add minimal registry and policy; run it green; add each read-only definition; run full backend checks; commit `feat(tools): add typed registry and authorization policy`.

**Constraints:** four read-only names only; no agent self-registration; no raw handler errors or sensitive audit parameters; default timeout 15 seconds; per-run maximum 12; no Celery, OIDC/RLS, or generic code/network tool.
