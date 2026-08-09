# Phase 4 Pre-research Evidence Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build offline, fail-closed evidence tooling for controlled Agent experiments, backend benchmarks, training-data governance, and platform-scale readiness without enabling any Phase 4 runtime capability.

**Architecture:** Four independent pure-Python packages accept validated observations or candidates and return structured decisions. They have no API, database, network, model, GPU, cloud, or production-Flow integration; external experiments produce inputs, while these packages enforce comparability and readiness gates.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, Ruff, mypy.

## Global Constraints

- Do not modify `backend/app/agents/flow.py`, Model Router, Tool Policy, database models, APIs, frontend, or deployment workflows.
- Do not call external models, download weights, create GPU/Kubernetes resources, or use production data.
- Synthetic observations may exist only inside tests and must never be reported as real Phase 4 evidence.
- Keep Agent capabilities read-only, `allow_delegation=False`, and `max_calls=1`.
- Default training readiness requires at least 300 approved train examples and 50--100 isolated holdout examples.
- Do not stage or modify `.superpowers/`.

---

### Task 1: Controlled Agent experiment gate

**Files:**
- Create: `backend/app/agents/capabilities.py`
- Create: `backend/app/agents/experiment.py`
- Test: `backend/tests/agent_eval/test_controlled_experiment.py`

**Interfaces:**
- Produces: `AgentCapability`, `AgentExperimentArm`, `ExperimentObservation`, `ExperimentDecision`, and `evaluate_controlled_experiment(observations, policy) -> ExperimentDecision`.
- Consumes: only validated offline observations; no runtime or model objects.

- [ ] **Step 1: Write failing tests** for read-only capability enforcement, identical three-arm case sets, fewer than 100 cases, a +5pp within-budget GO, and a cost/latency NO-GO.
- [ ] **Step 2: Run** `uv --cache-dir /private/tmp/p4-uv-cache run pytest backend/tests/agent_eval/test_controlled_experiment.py -q` and confirm import failure because the modules do not exist.
- [ ] **Step 3: Implement** strict Pydantic contracts, nearest-rank p95, per-arm metrics, and comparison against the token-matched arm with these public signatures:

```python
class AgentExperimentArm(StrEnum):
    BASELINE = "baseline"
    TOKEN_MATCHED = "token_matched"
    SPECIALIST = "specialist"

class AgentCapability(BaseModel):
    name: str
    input_schema: str
    output_schema: str
    allowed_tools: tuple[str, ...]
    max_calls: Literal[1] = 1
    max_cost_microusd: int
    required_eval_suite: str
    allow_delegation: Literal[False] = False
    read_only: Literal[True] = True

def evaluate_controlled_experiment(
    observations: Sequence[ExperimentObservation], policy: ExperimentPolicy
) -> ExperimentDecision: ...
```
- [ ] **Step 4: Re-run the test** and confirm all Task 1 cases pass.
- [ ] **Step 5: Commit** only Task 1 files with `feat(agents): add controlled specialist experiment gate`.

### Task 2: Backend benchmark evidence model

**Files:**
- Create: `backend/app/benchmarks/__init__.py`
- Create: `backend/app/benchmarks/backends.py`
- Test: `backend/tests/unit/benchmarks/test_backends.py`

**Interfaces:**
- Produces: `BackendModule`, `BackendKind`, `BackendDescriptor`, `BenchmarkObservation`, `BenchmarkSummary`, `BackendComparison`, `summarize_observations()` and `compare_backends()`.
- Consumes: observations produced by separately run OCR/Embedding/Rerank/Generation benchmarks.

- [ ] **Step 1: Write failing tests** for mixed-backend rejection, literal p50/p95/cost/failure summaries, insufficient evidence, quality regression, and a comparable candidate.
- [ ] **Step 2: Run** `uv --cache-dir /private/tmp/p4-uv-cache run pytest backend/tests/unit/benchmarks/test_backends.py -q` and confirm import failure.
- [ ] **Step 3: Implement** strict contracts, nearest-rank percentiles, serial throughput, case-set equality, quality floor/drop gates, and `INSUFFICIENT_EVIDENCE | NO_GO | EVIDENCE_READY` decisions with these public signatures:

```python
class BackendModule(StrEnum):
    OCR = "ocr"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    GENERATION = "generation"

def summarize_observations(
    observations: Sequence[BenchmarkObservation], *, minimum_cases: int
) -> BenchmarkSummary: ...

def compare_backends(
    control: Sequence[BenchmarkObservation],
    candidate: Sequence[BenchmarkObservation],
    policy: BackendComparisonPolicy,
) -> BackendComparison: ...
```
- [ ] **Step 4: Re-run the test** and confirm all Task 2 cases pass.
- [ ] **Step 5: Commit** only Task 2 files with `feat(benchmarks): add backend evidence comparison`.

### Task 3: Training candidate governance and export readiness

**Files:**
- Create: `backend/app/training/__init__.py`
- Create: `backend/app/training/schemas.py`
- Create: `backend/app/training/export.py`
- Test: `backend/tests/unit/training/test_export.py`

**Interfaces:**
- Produces: `TrainingCandidate`, `CandidateStatus`, `TrainingSplit`, `TrainingExportPolicy`, `TrainingExample`, `TrainingExportReport`, and `prepare_training_export(candidates, holdout_groups, policy) -> TrainingExportReport`.
- Consumes: `DataClassification` and `redact_sensitive_text()` from existing security modules.

- [ ] **Step 1: Write failing tests** for approved metadata, unknown fields, license/authorization failure, PII/Secret failure, deterministic group split/hash, duplicate IDs, and default readiness counts.
- [ ] **Step 2: Run** `uv --cache-dir /private/tmp/p4-uv-cache run pytest backend/tests/unit/training/test_export.py -q` and confirm import failure.
- [ ] **Step 3: Implement** fail-closed candidate validation, sensitive-text detection by redaction comparison, deterministic group assignment, canonical JSON hashing, rejection reasons, and readiness thresholds with these public signatures:

```python
class TrainingCandidate(BaseModel):
    sample_id: str
    task_type: str
    source_run_id: UUID
    workspace_id: UUID
    classification: DataClassification
    input_text: str
    expected_output: str
    tool_names: tuple[str, ...]
    labels: tuple[str, ...]
    approver_id: str
    approved_at: datetime
    license_id: str
    license_allows_training: bool
    training_authorized: bool
    split_group: str
    status: CandidateStatus

def prepare_training_export(
    candidates: Sequence[TrainingCandidate],
    *,
    holdout_groups: frozenset[str],
    policy: TrainingExportPolicy = TrainingExportPolicy(),
) -> TrainingExportReport: ...
```
- [ ] **Step 4: Re-run the test** and confirm all Task 3 cases pass.
- [ ] **Step 5: Commit** only Task 3 files with `feat(training): add governed candidate export gate`.

### Task 4: Platform capacity readiness gate

**Files:**
- Create: `backend/app/platform/__init__.py`
- Create: `backend/app/platform/capacity.py`
- Test: `backend/tests/unit/platform/test_capacity.py`
- Create: `docs/decisions/adr-phase4-preresearch-code.md`

**Interfaces:**
- Produces: `CapacityEvidence`, `PlatformScaleDecision`, and `evaluate_platform_scale(evidence) -> PlatformScaleDecision`.
- Consumes: only approved offline evidence fields; no cluster or cloud clients.

- [ ] **Step 1: Write failing tests** for fewer than 8 weeks, missing owner/budget/rollback, no technical trigger, and a fully evidenced `EVIDENCE_READY` result.
- [ ] **Step 2: Run** `uv --cache-dir /private/tmp/p4-uv-cache run pytest backend/tests/unit/platform/test_capacity.py -q` and confirm import failure.
- [ ] **Step 3: Implement** strict capacity evidence and the conjunction of observation window, technical trigger, owner, budget, and rollback prerequisites with these public signatures:

```python
class CapacityEvidence(BaseModel):
    observed_weeks: int
    ha_or_rto_missed: bool = False
    worker_scale_still_violates_slo: bool = False
    release_boundary_incidents: int = 0
    database_optimized_still_insufficient: bool = False
    platform_owner: str | None = None
    budget_approved: bool = False
    rollback_drilled: bool = False

def evaluate_platform_scale(evidence: CapacityEvidence) -> PlatformScaleDecision: ...
```
- [ ] **Step 4: Re-run the test** and confirm all Task 4 cases pass.
- [ ] **Step 5: Add the ADR** documenting that these modules are pre-research evidence tooling, not Phase 4 activation.
- [ ] **Step 6: Commit** only Task 4 files and the ADR with `feat(platform): add scale evidence readiness gate`.

### Task 5: Integration verification

**Files:**
- Modify: `docs/development/evaluation.md`

**Interfaces:**
- Documents exact offline commands and the distinction between evidence tooling and real runtime validation.

- [ ] **Step 1: Document** the three evidence tools and platform gate without claiming real Phase 4 evidence using these exact headings and command forms:

```markdown
## 阶段四预研证据工具

- `python -m backend.app.agents.experiment --input <observations.jsonl>`
- `python -m backend.app.benchmarks.backends --control <control.jsonl> --candidate <candidate.jsonl>`
- 训练导出和平台扩容判断只通过 Python API 使用，默认门禁不足时不产生可用训练集或平台实施批准。
```
- [ ] **Step 2: Run** `uv --cache-dir /private/tmp/p4-uv-cache run ruff check backend tests`.
- [ ] **Step 3: Run** `uv --cache-dir /private/tmp/p4-uv-cache run mypy backend`.
- [ ] **Step 4: Run** `uv --cache-dir /private/tmp/p4-uv-cache run pytest -q`.
- [ ] **Step 5: Run** frontend lint, typecheck, tests, and build because the repository acceptance gate requires them even though frontend is unchanged.
- [ ] **Step 6: Run** development Compose config and `git diff --check`.
- [ ] **Step 7: Commit** documentation with `docs: document phase four pre-research evidence tools`.
