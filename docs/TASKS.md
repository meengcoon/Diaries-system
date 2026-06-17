# Tasks

This is the single task queue. Future Codex runs should work on one task ID at a time.

## Status Definitions

- `PARKED`: idea only, do not implement
- `TODO`: valid task, not started
- `READY`: dependencies satisfied, can be implemented
- `IN_PROGRESS`: currently being worked on
- `BLOCKED`: blocked by dependency
- `DONE`: completed and verified
- `WONTFIX`: explicitly rejected

## DOCS-001 - Create Project Control Documents

Status: DONE

Scope:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/TASKS.md`

Acceptance:

- Three files exist.
- They do not contradict current project state.
- No application code is changed.
- No unrelated dirty files are staged or committed.

## TEST-001 - Commit Core E2E and Extreme Input Regression Tests

Status: READY

Goal:

Commit only the newly added regression tests that validate the core diary chain and input boundaries.

Allowed files:

- `tests/test_fake_provider_e2e.py`
- `tests/test_extreme_inputs.py`

Scope:

- Stage and commit only these two test files.
- Do not modify code.
- Do not modify docs.
- Do not stage unrelated dirty files.

Acceptance:

- Cached diff contains exactly:
  - `tests/test_fake_provider_e2e.py`
  - `tests/test_extreme_inputs.py`
- `.venv/bin/python -m pytest -q` passes.
- `.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py` passes.
- Commit message is:
  `test: cover diary core e2e and input limits`

Validation:

```bash
git diff --cached --name-only
git diff --cached --check
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
```

## DOCS-002 - Commit Project Control Documents

Status: READY

Depends on:

- `TEST-001`

Dependency status:

- Satisfied by `ed1a78e test: cover diary core e2e and input limits`

Goal:

Commit the project control documents after the current test baseline has been committed.

Allowed files:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/TASKS.md`
- `docs/WORKFLOW.md`

Scope:

- Review and commit only the four control-doc baseline files.
- Do not stage `README.md`.
- Do not stage `docs/operations.md`.
- Do not stage application code.
- Do not stage tests.
- Do not stage unrelated dirty or untracked files.

Acceptance:

- Cached diff contains exactly:
  - `AGENTS.md`
  - `docs/PROJECT_STATE.md`
  - `docs/TASKS.md`
  - `docs/WORKFLOW.md`
- `docs/PROJECT_STATE.md` accurately distinguishes committed baseline from current worktree validation.
- No unrelated dirty files are staged.
- `README.md`, `docs/operations.md`, application code, tests, and unrelated dirty or untracked files are not staged.
- Commit message is:
  `docs: add project control documents`

Validation:

```bash
git diff --cached --name-only
git diff --cached --check
```

## DOCS-003 - Require Tasks to Exist in TASKS Before Execution

Status: DONE

Goal:

Update `AGENTS.md` so future Codex runs must execute only tasks listed in `docs/TASKS.md`.

Allowed files:

- `AGENTS.md`
- `docs/TASKS.md`

Scope:

- Add a hard rule to `AGENTS.md`.
- If this task is newly added, update this task status to DONE after the AGENTS change is complete.
- Do not modify application code.
- Do not modify tests.

Acceptance:

- `AGENTS.md` clearly states that Codex must not execute or invent tasks that are not listed in `docs/TASKS.md`.
- `AGENTS.md` clearly states that if a needed task is missing, `docs/TASKS.md` must be updated first in a docs-only task.
- No application code or tests are changed.

## DOCS-004 - Add canonical workflow runbook

Status: DONE

Goal:

Create or complete a dedicated workflow document that records the exact operating process for future bugfixes, docs changes, features, validation, and commits.

Problem:

`AGENTS.md` contains hard rules and `docs/TASKS.md` contains the task queue, but there is no confirmed canonical document that records the full step-by-step operating workflow. This increases the risk that future prompts invent tasks, skip staging discipline, forget validation, or bypass the three-file management method.

Allowed files:

- `AGENTS.md`
- `docs/TASKS.md`
- `docs/WORKFLOW.md`
- `docs/operations.md` only if it already exists and is clearly the better canonical workflow location

Scope:

- Prefer creating `docs/WORKFLOW.md` as the canonical workflow runbook.
- If `docs/operations.md` already exists and clearly serves this exact purpose, update it instead and make it the canonical workflow document.
- Add a reference in `AGENTS.md` telling future Codex runs to read the workflow document before executing implementation tasks.
- Do not modify application code.
- Do not modify tests.
- Do not implement any bugfix or feature.

Acceptance:

- There is exactly one canonical workflow/runbook document.
- The workflow document explains the roles of:
  - `AGENTS.md`
  - `docs/PROJECT_STATE.md`
  - `docs/TASKS.md`
  - `docs/WORKFLOW.md` or the chosen canonical workflow file
- It records the standard operating process:
  - register task in `docs/TASKS.md`
  - read control docs
  - work on one task ID only
  - modify only allowed files
  - run validation
  - report changed files and risks
  - narrow-stage only explicit files
  - commit with focused message
  - update `docs/PROJECT_STATE.md` and `docs/TASKS.md` when appropriate
- It records the current planned sequence:
  1. commit core E2E and extreme input tests
  2. commit control documents
  3. audit dirty worktree
  4. repair or replace broken local virtualenv
  5. address FastAPI `on_event` deprecation warning
  6. add Health / Diagnostics API
  7. add Health / Diagnostics frontend panel
  8. write Quick Capture backend contract
  9. add text-only Quick Capture endpoint
  10. verify Quick Capture in the core chain
  11. design image attachment storage
  12. add attachment persistence
  13. add safe image ingest
  14. add Quick Capture image support
  15. define desktop Quick Capture approach
  16. build text-only desktop shell
  17. add desktop image paste / drag support
- `AGENTS.md` references the canonical workflow document.
- No application code or tests are changed.

Validation:

```bash
git diff -- AGENTS.md docs/TASKS.md docs/WORKFLOW.md docs/operations.md
git diff --check
```

## BUG-001 - Rebuild or Replace Broken Local Virtualenv

Status: DONE

Problem:

`.venv1/bin/python -m pytest` fails with `No module named pytest`.
`.venv1/bin/python -m pip --version` hangs.

Scope:

- Environment reproducibility only.
- Do not change application behavior.

Allowed files:

- `requirements-dev.txt`
- `README.md`
- `docs/PROJECT_STATE.md`
- possibly environment setup docs

Acceptance:

- Recommended venv Python can run `pip --version`.
- Recommended venv Python can run `python -m pytest -q`.
- README documents the recommended setup.
- `.venv/bin/python -m pytest -q` passed with 36 passed and 2 warnings.
- `.venv1` remains obsolete/broken.

Validation:

```bash
.venv/bin/python -m pip --version
.venv/bin/python -m pytest -q
```

## DOCS-005 - Reconcile BUG-001 Task Status After Virtualenv Fix

Status: DONE

Goal:

Update task bookkeeping after BUG-001 completed the virtualenv repair but could not update `docs/TASKS.md` because BUG-001's allowed file list omitted it.

Allowed files:

- `docs/TASKS.md`

Scope:

- Mark BUG-001 as DONE if its acceptance criteria are recorded as passed.
- Update BUG-001 validation commands to use `.venv/bin/python` instead of ambiguous system `python3`, if needed.
- Do not modify application code.
- Do not modify tests.
- Do not modify README.md.
- Do not modify `docs/PROJECT_STATE.md`.
- Do not stage or commit.

Acceptance:

- BUG-001 status is DONE.
- BUG-001 records that `.venv/bin/python -m pytest -q` passed with 36 passed.
- BUG-001 records that `.venv1` remains obsolete/broken.
- No files other than `docs/TASKS.md` are changed.

Validation:

```bash
git diff -- docs/TASKS.md
git diff --check
git diff --cached --name-only
```

## DOCS-006 - Add Task Completion Gates and Stop Conditions

Status: DONE

Goal:

Add explicit task completion gates and stop conditions so future Codex runs know when to stop instead of continuing to polish docs, broaden scope, or add unrelated implementation work.

Problem:

The current workflow defines how tasks start and how files are constrained, but it does not define a hard enough finish condition. This caused repeated markdown governance edits and could also happen during implementation tasks.

Allowed files:

- `AGENTS.md`
- `docs/TASKS.md`
- `docs/WORKFLOW.md`

Scope:

- Add a completion gate and stop-condition section to `docs/WORKFLOW.md`.
- Add a short hard rule to `AGENTS.md` requiring Codex to stop once the selected task's completion gate is satisfied.
- Update this DOCS-006 task status to DONE after the change.
- Do not modify application code.
- Do not modify tests.
- Do not modify README.md.
- Do not modify `docs/PROJECT_STATE.md`.
- Do not implement any bugfix or feature.

Acceptance:

- `docs/WORKFLOW.md` defines a Task Start Gate.
- `docs/WORKFLOW.md` defines a Task Completion Gate.
- `docs/WORKFLOW.md` defines Stop Conditions.
- `docs/WORKFLOW.md` defines an Anti-Loop Rule that prevents repeated governance/doc polishing once acceptance is met.
- `docs/WORKFLOW.md` says newly discovered issues should be recorded as separate tasks instead of fixed opportunistically.
- `AGENTS.md` says Codex must stop after the selected task's acceptance criteria and validation are satisfied.
- DOCS-006 is marked DONE.
- No files outside `AGENTS.md`, `docs/TASKS.md`, and `docs/WORKFLOW.md` are changed.

Validation:

```bash
git diff --check
git diff --cached --name-only
rg -n "Task Start Gate|Task Completion Gate|Stop Conditions|Anti-Loop Rule|stop after" AGENTS.md docs/WORKFLOW.md docs/TASKS.md
```

## DOCS-007 - Normalize Validation Interpreter to Project Virtualenv

Status: DONE

Goal:

Resolve the validation interpreter conflict that blocks TEST-001 by making the project virtualenv the canonical validation interpreter.

Problem:

`docs/PROJECT_STATE.md` records `.venv/bin/python -m pytest -q` as the current passing validation environment, while TEST-001 and the workflow validation defaults still reference ambiguous system `python3`. This blocks TEST-001 because the system Python may not have pytest.

Allowed files:

- `AGENTS.md`
- `docs/TASKS.md`
- `docs/WORKFLOW.md`

Scope:

- Update default validation commands in `AGENTS.md` and `docs/WORKFLOW.md` from ambiguous `python3` to `.venv/bin/python`.
- Update TEST-001 validation commands in `docs/TASKS.md` to use `.venv/bin/python`.
- Update any other task validation command in `docs/TASKS.md` that still uses ambiguous system-Python pytest or compileall for project validation.
- Mark DOCS-007 as DONE after the update.
- Do not modify application code.
- Do not modify tests.
- Do not modify README.md.
- Do not modify `docs/PROJECT_STATE.md`.

Acceptance:

- `AGENTS.md` uses `.venv/bin/python` for default pytest and compileall checks.
- `docs/WORKFLOW.md` uses `.venv/bin/python` for default pytest and compileall checks.
- TEST-001 uses `.venv/bin/python` for validation.
- No project validation command in `docs/TASKS.md` still uses ambiguous system-Python pytest or compileall commands.
- DOCS-007 is marked DONE.
- No files outside `AGENTS.md`, `docs/TASKS.md`, and `docs/WORKFLOW.md` are changed.

Validation:

```bash
git diff --check
git diff --cached --name-only
rg -n "python3 -m (pytest|compileall)" AGENTS.md docs/TASKS.md docs/WORKFLOW.md
rg -n "\.venv/bin/python -m pytest|\.venv/bin/python -m compileall|DOCS-007|Status: DONE" AGENTS.md docs/TASKS.md docs/WORKFLOW.md
```

## HEALTH-001 - Core Health / Diagnostics API

Status: TODO

Goal:

Add backend endpoint for core health state.

Scope:

- DB path
- entries count
- blocks count
- jobs pending/running/failed counts
- latest rollup
- FTS availability
- context_pack availability
- audio module available/disabled if easy to expose without importing heavy dependencies

Allowed files:

- `api/routes_health.py`
- `server.py`
- `storage/repo_*.py` only if needed
- `tests/test_health*.py`
- `docs/PROJECT_STATE.md`

Acceptance:

- Endpoint returns JSON health summary.
- Does not import audio-heavy modules.
- Tested for empty DB and DB with entries/jobs.
- Full pytest passes.

Validation:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
```

## HEALTH-002 - Core Health / Diagnostics Frontend Panel

Status: BLOCKED

Depends on:

- `HEALTH-001`

Scope:

- Add small frontend diagnostics panel/page.

Acceptance:

- Shows DB path.
- Shows job counts.
- Shows FTS status.
- Shows latest rollup.
- Does not render untrusted HTML.

## QC-001 - Quick Capture Backend Contract

Status: PARKED

Goal:

Design the backend contract for a future desktop Quick Capture companion. Do not implement.

Notes:

Quick Capture should support:

- global hotkey desktop shell later
- one small input box
- text notes
- optional image upload/paste/drag later
- save through backend API
- no direct DB writes
- no synchronous model calls

Depends on:

- `HEALTH-001`
- `HEALTH-002`

Deliverable:

- future `docs/quick_capture_contract.md`

## QC-002 - Quick Capture Text-Only Backend Endpoint

Status: BLOCKED

Depends on:

- `QC-001` accepted

Acceptance:

- Adds `POST /api/quick-captures`.
- Text-only first.
- Goes through existing ingest path.
- Enqueues jobs.
- Rejects empty text with no attachments.
- Does not import desktop/audio dependencies.
- Covered by tests.

## QC-003 - Image Attachment Ingest

Status: BLOCKED

Depends on:

- `QC-002`

Acceptance:

- Supports png/jpeg/webp only.
- Has per-file and per-request size limits.
- Stores by sha256 or generated safe filename.
- Does not trust original filename.
- Does not persist rejected files.
- Tests invalid MIME, oversized file, empty upload, and valid image.

## QC-004 - Desktop Quick Capture Shell

Status: BLOCKED

Depends on:

- `QC-002`
- `QC-003` if image support is included

Notes:

This should be a desktop companion, not a browser plugin. It should call the backend API and must not write directly to SQLite.
