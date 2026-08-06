# P2-02 Model Gateway and Prompt Budget Implementation Plan

> **For agentic workers:** Execute serially with `executing-plans`; do not dispatch subagents.

**Goal:** Centralize chat, review, and embedding model configuration behind a typed, mock-tested gateway with versioned prompts, retry classification, and per-run token/cost budgets.

**Architecture:** `ModelGateway` is a backend Protocol. The OpenAI-compatible adapter is injected with an SDK-shaped client and never instantiated by tests; it records normalized response usage and refuses unsupported capabilities. Prompt files plus a checked manifest provide immutable ID/version/SHA/variable/schema metadata. `LegacyModelAdapter` remains the compatibility path for `legacy/llm.py` and `legacy/agent.py`; no production call is moved until its test-covered gateway consumer exists.

**Tech Stack:** Python 3.12, Pydantic v2, OpenAI-compatible SDK, hashlib, pytest mocks; no network or paid model calls.

## Global Constraints

- Preserve Streamlit and LangGraph legacy behavior and do not remove the legacy adapter.
- Do not put API keys, prompt bodies, documents, or raw provider errors in logs or test fixtures.
- Retry only 429, connection-reset, and 5xx failures, at most twice; never retry validation, authorization, refusal, or budget errors.
- Keep safety rules and the current request when trimming context; remove only low-value history/repeated evidence.
- No live provider test, paid call, or new task queue belongs in P2-02.

### Task 1: Typed model contracts and retry classification

**Files:**
- Create: `backend/app/models/__init__.py`, `schemas.py`, `gateway.py`, `costs.py`
- Test: `backend/tests/unit/models/test_gateway.py`

**Interfaces:**

```python
class ModelGateway(Protocol):
    async def complete(self, request: ModelRequest, timeout_seconds: float) -> ModelResponse: ...

class ModelBudgetExceeded(Exception): ...
class ProviderCapabilityError(Exception): ...
```

- [ ] Write a failing test that a 429 succeeds on its third attempt but a 401 raises without retry.
- [ ] Run `uv run pytest backend/tests/unit/models/test_gateway.py -q`; expect missing module failure.
- [ ] Implement request/response/usage/capability schemas plus a retry classifier that returns `True` only for 429, reset, and 5xx.
- [ ] Re-run the focused test; expect pass.

### Task 2: OpenAI-compatible and legacy adapters

**Files:**
- Create: `backend/app/models/openai_compatible.py`, `router.py`
- Create: `backend/app/models/legacy.py`
- Modify: `backend/app/core/config.py`, `legacy/llm.py`, `legacy/agent.py`
- Test: `backend/tests/unit/models/test_openai_compatible.py`

**Interfaces:**

```python
adapter = OpenAICompatibleGateway(client, provider="openai-compatible", capabilities=ModelCapabilities())
response = await adapter.complete(ModelRequest(...), timeout_seconds=10)
legacy = LegacyModelAdapter()
```

- [ ] Write failing mock tests for 5xx retry, timeout, missing usage, malformed output schema, and unsupported stream/tool capabilities.
- [ ] Run focused tests; expect the adapter import to fail.
- [ ] Implement the adapter with bounded retry, measured latency, missing-usage normalization, and safe error codes; use configuration `CHAT_MODEL`, `REVIEW_MODEL`, and `EMBED_MODEL` rather than literals.
- [ ] Keep `LegacyModelAdapter` delegating to the legacy module so callers can roll back without restoring hardcoded models.
- [ ] Re-run focused tests; expect pass with no HTTP request.

### Task 3: Versioned prompt manifest and context budget

**Files:**
- Create: `backend/app/prompts/analyst/v1/system.md`, `backend/app/prompts/reviewer/v1/system.md`, `backend/app/prompts/manifest.py`
- Test: `backend/tests/unit/prompts/test_manifest.py`

**Interfaces:**

```python
manifest = load_prompt_manifest("analyst", "v1")
context = build_context(safety_rules, current_request, run_state, evidence, summary, budget)
```

- [ ] Write a failing test asserting SHA changes when prompt text changes, missing variables fail safely, and trimming retains safety/current request.
- [ ] Run focused test; expect module-not-found failure.
- [ ] Implement immutable manifest fields `id`, `version`, `sha256`, `required_variables`, `output_schema`, and `evaluation_version`; derive SHA from file bytes.
- [ ] Implement ordered context assembly and reject a request when retained content still exceeds token/cost budgets.
- [ ] Re-run focused tests; expect pass.

### Task 4: Persist model accounting on Runs and document the boundary

**Files:**
- Modify: `backend/app/domain/agent_runs/{models,schemas,service}.py`
- Create: `backend/alembic/versions/20260806_p2_02_model_accounting.py`
- Modify: `docs/api/overview.md`, `docs/architecture/overview.md`, `.env.example` if it exists
- Test: `backend/tests/integration/test_model_accounting_postgres.py`

- [ ] Write a failing disposable-PostgreSQL test that a completed mock call records provider/model/token/cost/latency/error code without prompt text.
- [ ] Run it against `TEST_DATABASE_URL`; expect failure before migration.
- [ ] Add nullable/non-destructive accounting columns and service updates; do not alter P2-01 event semantics.
- [ ] Re-run focused integration test; expect pass.

### Task 5: Full verification and commit

- [ ] Run backend model/prompt tests, all offline backend tests, Ruff, mypy, frontend checks only if frontend changes, disposable PostgreSQL migration tests, `git diff --check`, staged secret/PII scan, and staged-path inspection.
- [ ] Commit only P2-02 paths with `feat(models): add versioned model gateway and prompt budget`.
- [ ] Record actual commands, skipped live-provider tests, rollback via `LegacyModelAdapter`, and the commit hash before starting P2-03.

## Plan self-review

P2-02 covers the gateway Protocol, OpenAI-compatible capability checks, bounded transient retry, usage/cost/latency normalization, prompt file+manifest versioning, ordered context trimming, run budgets, and Legacy rollback. It intentionally excludes CrewAI, Tool Registry, live provider calls, RAG/OCR, production authentication, Celery, and frontend feature work.
