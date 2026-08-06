# P2-01 Agent Runs and SSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` task-by-task. This plan is explicitly serial: do not dispatch subagents.

**Goal:** Add PostgreSQL-backed, development-only Agent Runs that can be created, queried, cancelled, and replayed through ordered SSE events, with a refresh-resilient Next.js panel.

**Architecture:** FastAPI persists every state transition and event through one `AgentRunRepository`; the `DevelopmentRunExecutor` is deliberately an in-process `asyncio.create_task` adapter and is labelled `development_only`. SSE only reads persisted events, using their integer sequence as the event ID, so reconnects never depend on process memory. Until P3 OIDC/RLS exists, request headers provide an explicit test-only principal/workspace boundary; this must not be documented as production authentication.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy async, Alembic, PostgreSQL, Next.js 15, TypeScript, Vitest.

## Global Constraints

- Preserve every `legacy/` Streamlit module and add no new Streamlit behavior.
- Use `/api/v1`, REST resources, and SSE only; do not add WebSocket or FastAPI `BackgroundTasks`.
- Persist state and events before returning/sending them; Redis, Celery, model calls, and paid APIs are out of scope.
- Executor is `development_only`; a P3 worker replaces it without changing the repository or HTTP contracts.
- Do not log prompt text, documents, credentials, or raw model/tool payloads.
- A terminal run (`completed`, `failed`, `cancelled`) is immutable; cancellation is idempotent.
- Keep `.superpowers/` and unrelated user files out of all staging and commits.

---

### Task 1: Define the persisted run contract and migration

**Files:**
- Create: `backend/app/domain/agent_runs/__init__.py`
- Create: `backend/app/domain/agent_runs/models.py`
- Create: `backend/app/domain/agent_runs/schemas.py`
- Modify: `backend/app/db/base.py`
- Create: `backend/alembic/versions/20260806_p2_01_create_agent_runs.py`
- Test: `backend/tests/api/test_agent_run_sse.py`

**Interfaces:**
- Produces `AgentRun`, `AgentRunEvent`, and `ConversationMessage` SQLAlchemy models.
- Produces `AgentRunStatus`, `CreateAgentRunRequest`, `AgentRunResponse`, and `AgentRunEventResponse` Pydantic contracts.
- `AgentRunEvent.sequence` is a positive per-run integer and has a database unique constraint with `run_id`.

- [ ] **Step 1: Write the failing API contract test**

```python
def test_create_run_returns_202_with_persisted_queued_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agent/runs",
        json={"question": "总结贵州茅台的估值风险"},
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["executor_mode"] == "development_only"
```

- [ ] **Step 2: Run the test to verify it fails because the route and schema do not exist**

Run: `UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/api/test_agent_run_sse.py::test_create_run_returns_202_with_persisted_queued_contract -q`

Expected: FAIL with HTTP `404` or missing import; do not proceed on a typo/fixture failure.

- [ ] **Step 3: Implement the smallest contract and schema migration**

```python
class AgentRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class CreateAgentRunRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
```

Migration creates `agent_runs`, `agent_run_events`, and `conversation_messages`, including FK/indexes for `(workspace_id, created_at)` and `(run_id, sequence)`; it does not create identity/RLS tables.

- [ ] **Step 4: Run the focused test again**

Run: `UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/api/test_agent_run_sse.py::test_create_run_returns_202_with_persisted_queued_contract -q`

Expected: PASS using the repository fake; a real PostgreSQL migration test belongs to Task 5.

### Task 2: Persist events and enforce run state transitions

**Files:**
- Create: `backend/app/domain/agent_runs/repository.py`
- Create: `backend/app/domain/agent_runs/service.py`
- Modify: `backend/app/domain/agent_runs/models.py`
- Test: `backend/tests/api/test_agent_run_sse.py`

**Interfaces:**
- `AgentRunRepository.create_run(principal: DevelopmentPrincipal, question: str) -> AgentRunRecord`
- `AgentRunRepository.append_event(run_id, event_type, payload) -> AgentRunEventRecord`
- `AgentRunService.cancel(run_id, principal) -> AgentRunRecord`
- `AgentRunService.list_events(run_id, after_sequence) -> list[AgentRunEventRecord]`

- [ ] **Step 1: Add failing behavior tests**

```python
def test_events_are_sequenced_and_reconnect_reads_only_later_events(service: AgentRunService) -> None:
    run = service.create(DEMO_PRINCIPAL, "研究估值")
    first = service.append_event(run.id, "run.started", {})
    second = service.append_event(run.id, "text.delta", {"text": "草稿"})

    assert [event.sequence for event in service.list_events(run.id, after_sequence=first.sequence)] == [second.sequence]

def test_terminal_run_cannot_be_cancelled_again_or_transitioned(service: AgentRunService) -> None:
    run = service.create(DEMO_PRINCIPAL, "研究估值")
    service.cancel(run.id, DEMO_PRINCIPAL)
    assert service.cancel(run.id, DEMO_PRINCIPAL).status is AgentRunStatus.CANCELLED
```

- [ ] **Step 2: Verify both tests fail because no repository/service behavior exists**

Run: `UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/api/test_agent_run_sse.py -q`

Expected: FAIL for absent service methods, not for database connectivity.

- [ ] **Step 3: Implement transactionally persisted behavior**

```python
async def append_event(self, run_id: UUID, event_type: str, payload: dict[str, object]) -> AgentRunEvent:
    run = await self._locked_run(run_id)
    event = AgentRunEvent(run_id=run.id, sequence=run.next_sequence, event_type=event_type, payload=payload)
    run.next_sequence += 1
    self.session.add(event)
    await self.session.flush()
    return event
```

The service authorizes every read/mutation against both immutable `principal_id` and `workspace_id`; unauthorized and unknown runs both return a safe not-found result. It only permits `queued -> running -> terminal` and `queued/running -> cancelled`.

- [ ] **Step 4: Verify the focused behavior tests pass**

Run: `UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/api/test_agent_run_sse.py -q`

Expected: PASS; duplicate events are never synthesized by reconnect code.

### Task 3: Add the development-only executor and SSE HTTP boundary

**Files:**
- Create: `backend/app/domain/agent_runs/executor.py`
- Create: `backend/app/api/v1/agent_runs.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/api/test_agent_run_sse.py`

**Interfaces:**
- `RunExecutor.development_only: bool`
- `DevelopmentRunExecutor.submit(run_id) -> None`
- `POST /agent/runs`, `GET /agent/runs/{run_id}`, `GET /agent/runs/{run_id}/events`, `POST /agent/runs/{run_id}/cancel`
- Settings: `agent_run_timeout_seconds=180`, `agent_max_steps=8`, `sse_heartbeat_seconds=15`.

- [ ] **Step 1: Add failing HTTP tests for ordering, heartbeat, cancellation, and isolation**

```python
def test_sse_uses_persisted_sequence_as_id_and_last_event_id_replays_no_duplicates(client: TestClient) -> None:
    run = create_run(client)
    first_body = client.get(f"/api/v1/agent/runs/{run}/events", headers=DEMO_HEADERS).text
    last_id = last_sse_id(first_body)
    reconnect = client.get(f"/api/v1/agent/runs/{run}/events", headers=DEMO_HEADERS | {"Last-Event-ID": last_id})

    assert "id: " not in reconnect.text
    assert "event: heartbeat" in reconnect.text

def test_other_principal_cannot_read_or_cancel_run(client: TestClient) -> None:
    run = create_run(client)
    assert client.get(f"/api/v1/agent/runs/{run}", headers=OTHER_HEADERS).status_code == 404
    assert client.post(f"/api/v1/agent/runs/{run}/cancel", headers=OTHER_HEADERS).status_code == 404
```

- [ ] **Step 2: Run the focused test file and confirm the expected missing-route failure**

Run: `UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/api/test_agent_run_sse.py -q`

Expected: FAIL because event endpoint, executor, and header principal dependency are absent.

- [ ] **Step 3: Implement the minimal transport**

```python
async def event_stream() -> AsyncIterator[bytes]:
    for event in await service.list_events(run_id, after_sequence=last_event_id):
        yield encode_sse(event.sequence, event.event_type, event.payload)
    yield encode_sse(None, "heartbeat", {"run_id": str(run_id)})
```

`POST` persists a `queued` run, schedules `DevelopmentRunExecutor` with `asyncio.create_task`, and immediately returns `202`; it never uses `BackgroundTasks`. The executor checks cancellation/time limits only at step boundaries and emits `run.started`, `step.started`, `text.delta`, `review.required`, and exactly one terminal event. Event encoding uses `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, and `id: <sequence>`.

- [ ] **Step 4: Run focused API tests**

Run: `UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/api/test_agent_run_sse.py -q`

Expected: PASS for 202 response, sequence order, reconnect, heartbeat, timeout, cancellation, terminal immutability, and not-found isolation.

### Task 4: Add a refresh-resilient Next.js Agent Run panel

**Files:**
- Create: `frontend/lib/sse/agent-events.ts`
- Create: `frontend/components/agent-run-panel.tsx`
- Create: `frontend/app/agent-runs/page.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/globals.css`
- Modify: `frontend/lib/api/types.ts`
- Test: `frontend/tests/agent-run-panel.test.tsx`

**Interfaces:**
- `readAgentEvents(response, lastEventId) -> AsyncIterable<AgentEvent>` parses SSE `id`, `event`, and JSON `data`.
- The panel stores only the current `run_id` in `localStorage`, fetches `GET /agent/runs/{id}` on mount, then reconnects using the last event sequence.
- `POST /agent/runs/{id}/cancel` is used by the visible cancel control.

- [ ] **Step 1: Write failing UI tests**

```tsx
it("restores the saved run after a page refresh and reconnects after its last event", async () => {
  window.localStorage.setItem("investment-agent:last-run", "run-1");
  vi.stubGlobal("fetch", fakeRunThenSse([{ id: 2, event: "text.delta", data: { text: "草稿" } }]));

  render(<AgentRunPanel />);

  expect(await screen.findByText("草稿")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/runs/run-1/events"), expect.objectContaining({ headers: expect.objectContaining({ "Last-Event-ID": "0" }) }));
});
```

- [ ] **Step 2: Run the UI test and verify it fails because the panel/module does not exist**

Run: `npm --prefix frontend run test -- agent-run-panel`

Expected: FAIL with module-not-found; do not create implementation before observing this failure.

- [ ] **Step 3: Implement fetch-based SSE and the smallest panel**

```ts
export async function* readAgentEvents(response: Response): AsyncGenerator<AgentEvent> {
  const reader = response.body?.getReader();
  if (!reader) return;
  // Decode blank-line-delimited SSE records, retaining id/event/data fields.
}
```

Panel asks a question, displays persisted status/events, saves its returned run ID only after a successful 202 response, handles a terminal event without reconnect loops, and shows a safe generic error. It must not claim production authentication; development headers are isolated in one API helper.

- [ ] **Step 4: Run focused UI tests**

Run: `npm --prefix frontend run test -- agent-run-panel`

Expected: PASS for creation, refresh recovery, Last-Event-ID reconnect, terminal state, and cancel control.

### Task 5: Run migrations and cross-stack verification

**Files:**
- Modify: `docs/api/overview.md`
- Modify: `docs/architecture/overview.md`
- Test: `backend/tests/integration/test_agent_runs_postgres.py`

**Interfaces:**
- Documentation states the four run endpoints, the development-only executor limitation, and the temporary explicit test principal headers.
- The PostgreSQL integration test uses a disposable `TEST_DATABASE_URL`; it validates Alembic from an empty database and persisted reload/replay behavior.

- [ ] **Step 1: Write the failing PostgreSQL integration test**

```python
def test_migration_persists_events_before_sse_replay(migrated_settings: Settings) -> None:
    client = TestClient(create_app(migrated_settings))
    run_id = create_run(client)
    assert "event: run.started" in client.get(f"/api/v1/agent/runs/{run_id}/events", headers=DEMO_HEADERS).text
```

- [ ] **Step 2: Run it only when `TEST_DATABASE_URL` is a disposable empty database**

Run: `TEST_DATABASE_URL="$TEST_DATABASE_URL" UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/integration/test_agent_runs_postgres.py -q`

Expected: initially FAIL before the migration/repository path exists; then PASS after Tasks 1-3. Do not target a user or production database.

- [ ] **Step 3: Document the actual behavior and limitation**

Add endpoint examples, `Last-Event-ID` semantics, `heartbeat`, cancellation idempotence, and the fact that process restart preserves query/replay data but does not make the in-process executor production-recoverable.

- [ ] **Step 4: Run all P2-01 verification gates**

Run:

```bash
UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/api/test_agent_run_sse.py -q
UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest -q
UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run ruff check .
UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run mypy backend/app legacy/scoring.py
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
git diff --check
```

Also inspect staged paths and scan the staged diff for common credential/PII markers. Record the skipped PostgreSQL integration command if no disposable database is available.

- [ ] **Step 5: Commit only the P2-01 files**

```bash
git add backend/app/domain/agent_runs backend/app/api/v1/agent_runs.py backend/app/api/router.py backend/app/main.py backend/app/core/config.py backend/app/db/base.py backend/alembic/versions/20260806_p2_01_create_agent_runs.py backend/tests/api/test_agent_run_sse.py backend/tests/integration/test_agent_runs_postgres.py frontend/lib/sse/agent-events.ts frontend/components/agent-run-panel.tsx frontend/app/agent-runs/page.tsx frontend/app/page.tsx frontend/app/globals.css frontend/lib/api/types.ts frontend/tests/agent-run-panel.test.tsx docs/api/overview.md docs/architecture/overview.md docs/superpowers/plans/2026-08-06-p2-01-agent-runs-sse.md
git diff --cached --check
git commit -m "feat(agent-runs): add persistent runs and SSE events"
```

Do not stage `.superpowers/`, generated frontend output, virtual environments, or unrelated user files.

## Plan self-review

- Spec coverage: Tasks 1-3 cover persisted Run/Event/Conversation tables, 202 create, event sequencing, reconnect, heartbeat, cancellation, timeout, principal isolation, and a labelled development executor. Task 4 covers refresh recovery. Task 5 covers migration/documentation/full verification.
- Explicit exclusions: no model gateway, tool registry, CrewAI, Celery/Redis, WebSocket, paid/model networking, production authentication, or Streamlit changes.
- Deferred limitation: a process restart retains Run/Event query and SSE replay state, but an in-process executor cannot reliably resume execution; P3-03 is the required production recovery boundary.
