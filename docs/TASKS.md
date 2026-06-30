# Tasks

This is the single task queue. Future Codex runs should work on one task ID at a time.

For low-token runs, treat this file as the task queue/index. Use `rg` or line
ranges to find the selected task, then read `docs/tasks/<TASK_ID>/`, legacy
`docs/tasks/<TASK_ID>.md`, or an ignored `CURRENT_TASK.md` scratch file when a
task points to one.

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

Status: DONE

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

Status: DONE

Completed evidence:

- Completed by `2f6dd8b docs: add project control documents`, which committed
  `AGENTS.md`, `docs/PROJECT_STATE.md`, `docs/TASKS.md`, and
  `docs/WORKFLOW.md`.

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

## DOCS-008 - Optimize Governance Docs for Low-Token Task Capsules

Status: DONE

Completed evidence:

- Added the low-token markdown read policy to `AGENTS.md` and
  `docs/WORKFLOW.md`.
- Defined ignored `CURRENT_TASK.md` active-task capsules.
- Added `docs/tasks/DOCS-008.md` as the first per-task capsule and kept this row
  as an index entry.
- No application source files or tests were changed.

Task capsule:

- `docs/tasks/DOCS-008.md`

Depends on:

- `REPO-002`

Dependency status:

- Satisfied: `REPO-002` audit findings are recorded in committed task-queue
  evidence, and the follow-up cleanup chain through `REPO-011` has handled the
  dirty-worktree buckets that blocked docs-structure work.
- `REPO-012` only unblocks this task for a future selected run; it did not
  execute `DOCS-008`.

Goal:

Optimize the current four-file governance system so future Codex runs read less markdown context while preserving task discipline, scope control, validation gates, and stop conditions.

Validation:

```bash
git diff --check
git diff --cached --name-only
rg -n "DOCS-008|low-token|CURRENT_TASK|large markdown|task capsule" docs/TASKS.md AGENTS.md docs/WORKFLOW.md docs/PROJECT_STATE.md
```

## DOCS-009 - Codify Dirty Worktree and Task Boundary Rules

Status: DONE

Goal:

Codify reusable dirty-worktree, task-boundary, staging, validation, and final-response rules so future Codex prompts can be shorter.

Allowed files:

- `AGENTS.md`
- `docs/WORKFLOW.md`
- `docs/TASKS.md` only for task status bookkeeping

Scope:

- In `AGENTS.md`, add or refine permanent rules covering dirty-worktree preflight, unrelated dirty/untracked files, one-task execution, task-registration-only handling, scope boundaries, explicit staging, focused commits, and stopping after a successful task commit.
- In `docs/WORKFLOW.md`, add or refine workflow rules covering missing-task handling, dirty-worktree preflight, focused validation before broader validation, required pre-commit diff checks, out-of-scope validation blockers, final response labels, and final response evidence fields.
- Keep edits concise; tighten or consolidate existing rules instead of duplicating them.
- Do not touch `.gitignore`, `workers/analysis_worker.py`, `desktop_app.py`, source files, test files, untracked files, or implementation code.
- Do not start `WORKER-LOOP-001`, `DESKTOP-001`, `REPO-008`, `BUG-002`, `HEALTH-001`, Quick Capture, `DOCS-008`, or any other task.
- Do not combine this task with any other registration, implementation, cleanup, or refactor work.

Acceptance:

- `AGENTS.md` clearly codifies dirty-worktree, task-boundary, staging, commit, and stop-after-commit rules.
- `docs/WORKFLOW.md` clearly codifies missing-task handling, dirty-worktree preflight, validation ordering, pre-commit diff checks, out-of-scope validation blockers, and final response requirements.
- Final response labels include `PASS_AND_COMMITTED`, `TASK_REGISTERED_ONLY`, `BLOCKED`, and `STOPPED`.
- Final response requirements include selected task, files modified, files staged, commit hash if committed, validation commands run, final git status, and confirmation that unrelated dirty/untracked files were not touched.
- No files outside the allowed execution scope are changed.

Validation:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
rg -n "dirty worktree|unrelated dirty|git add \\.|staged diff|one task|TASK_REGISTERED_ONLY|PASS_AND_COMMITTED|BLOCKED|STOPPED|git diff --check|git diff --cached --name-only|git diff --cached --check" AGENTS.md docs/WORKFLOW.md
```

## REPO-001 - Audit Dirty Worktree

Status: DONE

Completed evidence:

- Committed task-queue evidence in `b2598a6 docs: record repository cleanup
  tasks` records that `REPO-001` identified dirty and untracked files before
  `REPO-002` inspected the diffs.
- Later committed cleanup and validation tasks handled the dirty-worktree
  buckets before `REPO-012` reconciliation.

Goal:

Audit the remaining dirty and untracked worktree files after the core test baseline and control documents have been committed.

Problem:

The repository still contains unrelated dirty and untracked files. Before starting BUG-002, HEALTH-001, or Quick Capture work, the remaining worktree state must be classified so future tasks do not accidentally touch or commit unrelated changes.

Allowed files:

- `docs/TASKS.md`

Scope:

- Audit only.
- Do not modify file contents.
- Do not stage files.
- Do not commit.
- Do not delete files.
- Classify files into A/B/C/D buckets:
  - A. likely real changes that should be preserved or committed later
  - B. likely temporary/generated files that should be ignored or removed later
  - C. historical residual files to leave untouched for now
  - D. uncertain files requiring user decision
- Identify files that are risky to leave dirty before BUG-002 or HEALTH-001.
- Recommend the next task after the audit.

Acceptance:

- Report tracked dirty files.
- Report untracked files.
- Classify files into A/B/C/D buckets.
- Identify immediate blockers for future code tasks.
- Recommend the next task.
- Confirm no files were modified, staged, committed, or deleted.

Validation:

```bash
git status --short
git diff --name-only
git ls-files --others --exclude-standard
git diff --cached --name-only
```

## REPO-002 - Inspect Dirty Worktree Diffs

Status: DONE

Completed evidence:

- Committed task-queue evidence records that `REPO-002` identified source/test
  dirty-change buckets that became `REPO-005` and follow-up tasks.
- The follow-up chain was committed through `REPO-011`, including task
  registration, source/test validation commits, optional desktop cleanup,
  pytest stabilization, and stale compileall cleanup.

Goal:

Inspect the actual diffs of the remaining dirty and untracked worktree files after REPO-001, without modifying, staging, committing, or deleting anything.

Problem:

REPO-001 identified many dirty and untracked files, including application code, services, storage, workers, tests, `README.md`, `docs/TASKS.md`, `docs/operations.md`, and `desktop_app.py`. Before starting BUG-002, HEALTH-001, DOCS-008, or Quick Capture work, these changes must be understood so future tasks do not accidentally mix historical changes with new work.

Allowed files:

- `docs/TASKS.md`

Scope:

- Audit only.
- Do not modify file contents.
- Do not stage files.
- Do not commit.
- Do not delete files.
- Inspect tracked diffs with focused commands.
- Inspect untracked file summaries without editing them.
- Classify each dirty or untracked file into:
  - A. task bookkeeping / docs that should be committed soon
  - B. environment documentation that should be committed separately
  - C. likely real code/test work that needs its own task or commit
  - D. likely obsolete/generated/residual files
  - E. uncertain files requiring user decision
- Recommend a concrete next action for each bucket.

Acceptance:

- Reports a grouped summary of tracked diffs.
- Reports a grouped summary of untracked files.
- Identifies whether `README.md` should be committed separately for BUG-001.
- Identifies whether `docs/TASKS.md` should be committed as task bookkeeping.
- Identifies which source/test files require separate investigation before BUG-002 or HEALTH-001.
- Identifies whether `docs/operations.md` should remain untracked, be committed later, or require user decision.
- Identifies whether `desktop_app.py` should remain untracked, be committed later, or require user decision.
- Recommends the next task.
- Confirms no files were modified, staged, committed, or deleted.

Validation:

```bash
git status --short
git diff --stat
git diff --name-only
git diff -- README.md docs/TASKS.md .gitignore
git diff -- api/routes_meta.py block_analyze.py llm/ollama_client.py
git diff -- services/analysis_jobs.py services/analysis_runner.py services/analysis_service.py services/audio_ingest_service.py
git diff -- storage/repo_entries.py storage/repo_jobs.py workers/analysis_worker.py
git diff -- tests/test_repo_jobs_claim.py
git ls-files --others --exclude-standard
git diff --cached --name-only
```

## REPO-003 - Commit task bookkeeping updates

Status: DONE

Completed evidence:

- Completed by `b2598a6 docs: record repository cleanup tasks`, which committed
  only `docs/TASKS.md` for the repository-cleanup task bookkeeping.

Goal:

Commit the current `docs/TASKS.md` bookkeeping updates created during the dirty worktree audit sequence.

Problem:

After the control-doc baseline commit, new task bookkeeping was added to `docs/TASKS.md` for REPO-001, REPO-002, and DOCS-008. These updates should be committed before further cleanup or implementation tasks so the task queue is no longer dependent on uncommitted working-tree state.

Allowed files:

- `docs/TASKS.md`

Scope:

- Commit only `docs/TASKS.md`.
- Do not modify application code.
- Do not modify tests.
- Do not modify `README.md`.
- Do not stage `README.md`.
- Do not stage `docs/operations.md`.
- Do not stage `AGENTS.md`, `docs/PROJECT_STATE.md`, or `docs/WORKFLOW.md` unless they are unexpectedly required by this task, in which case stop and report.
- Do not stage unrelated dirty or untracked files.

Acceptance:

- `docs/TASKS.md` includes REPO-001, REPO-002, and DOCS-008.
- `docs/TASKS.md` records REPO-001 and REPO-002 as completed or audit-executed if that status is already reflected; otherwise do not invent completion state.
- Cached diff contains exactly `docs/TASKS.md`.
- Commit message subject is:
  `docs: record repository cleanup tasks`
- No other files are staged or committed.

Validation:

```bash
git status --short
rg -n "REPO-001|REPO-002|DOCS-008" docs/TASKS.md
git diff --cached --name-only
git diff --cached --check
```

## REPO-004 - Resolve environment operations docs

Status: DONE

Goal:

Resolve and commit the remaining environment documentation changes from BUG-001 without mixing them with application code or unrelated dirty files.

Problem:

`README.md` is modified with `.venv` setup and runtime/queue notes. It references `docs/operations.md`, but `docs/operations.md` is currently untracked and still contains stale `.venv1` commands. Before code tasks resume, environment docs should be made internally consistent and committed separately.

Allowed files:

- `README.md`
- `docs/operations.md`
- `docs/TASKS.md`

Scope:

- Inspect the `README.md` diff and `docs/operations.md` content.
- Decide whether `docs/operations.md` should be committed as the runtime operations document.
- If keeping `docs/operations.md`, update stale `.venv1` references to `.venv` and make it consistent with `README.md`.
- If not keeping `docs/operations.md`, remove or adjust `README.md` references to it.
- Do not modify application code.
- Do not modify tests.
- Do not modify `AGENTS.md`.
- Do not modify `docs/PROJECT_STATE.md`.
- Do not modify `docs/WORKFLOW.md`.
- Do not stage unrelated dirty or untracked files.

Acceptance:

- `README.md` no longer references a stale or untracked operations document.
- `docs/operations.md` is either:
  - updated to `.venv` and committed with `README.md`, or
  - intentionally left untracked and `README.md` no longer depends on it.
- No `.venv1` commands remain in committed environment docs.
- Cached diff contains only `README.md`, `docs/operations.md` if included, and `docs/TASKS.md` only if marking REPO-004 DONE.
- Validation passes.
- Commit message subject is:
  `docs: document virtualenv operations`

Validation:

```bash
git status --short
rg -n "\.venv1|\.venv|operations.md|queue|worker" README.md docs/operations.md || true
git diff -- README.md docs/TASKS.md
git diff --cached --name-only
git diff --cached --check
```

## REPO-005 - Investigate existing source and test dirty changes

Status: DONE

Completed evidence:

- Completed earlier as `AUDIT_COMPLETE_READ_ONLY`.

Goal:

Inspect and classify the remaining source/test dirty changes before starting BUG-002, HEALTH-001, DOCS-008, or Quick Capture work.

Problem:

REPO-002 identified real source/test dirty changes across API, services, storage, workers, LLM, and tests. These changes may represent unfinished historical work. They must be understood before new implementation tasks begin, otherwise future commits may accidentally mix unrelated old changes with new work.

Allowed files:

- `docs/TASKS.md`

Scope:

- Audit only.
- Do not modify file contents.
- Do not stage files.
- Do not commit.
- Do not delete files.
- Inspect diffs for:
  - `.gitignore`
  - `api/routes_meta.py`
  - `block_analyze.py`
  - `llm/ollama_client.py`
  - `services/analysis_jobs.py`
  - `services/analysis_runner.py`
  - `services/analysis_service.py`
  - `services/audio_ingest_service.py`
  - `storage/repo_entries.py`
  - `storage/repo_jobs.py`
  - `workers/analysis_worker.py`
  - `tests/test_repo_jobs_claim.py`
  - untracked `tests/*.py`
  - `desktop_app.py`
- Classify each file into:
  - A. should be committed as a coherent existing feature/fix
  - B. should be split into multiple future tasks
  - C. should be reverted/removed later
  - D. should be left untouched for now
  - E. requires user decision
- Recommend the next concrete task after investigation.

Acceptance:

- Reports what each dirty source/test file appears to change.
- Identifies coherent groups of related files.
- Identifies whether any group appears safe to commit soon.
- Identifies which files must not be touched before BUG-002 or HEALTH-001.
- Recommends next task.
- Confirms no files were modified, staged, committed, or deleted.

Validation:

```bash
git status --short
git diff --stat
git diff --name-only
git diff -- .gitignore
git diff -- api/routes_meta.py block_analyze.py llm/ollama_client.py
git diff -- services/analysis_jobs.py services/analysis_runner.py services/analysis_service.py services/audio_ingest_service.py
git diff -- storage/repo_entries.py storage/repo_jobs.py workers/analysis_worker.py
git diff -- tests/test_repo_jobs_claim.py
git ls-files --others --exclude-standard tests
git diff --cached --name-only
```

## REPO-006 - Commit REPO-005 task bookkeeping

Status: DONE

Completed evidence:

- Completed by commit `3309a6a docs: record REPO-005 audit task`.

Goal:

Commit only the `docs/TASKS.md` bookkeeping that registered REPO-005 after the read-only source/test dirty-change audit.

Problem:

REPO-005 was registered in `docs/TASKS.md` so the source/test dirty-change audit could be executed safely. That task bookkeeping now needs its own narrow docs-only commit before BUG-002, HEALTH-001, DOCS-008, Quick Capture, or any source/test cleanup work starts.

Allowed files:

- `docs/TASKS.md`

Scope:

- Commit only `docs/TASKS.md`.
- Do not modify application code.
- Do not modify tests.
- Do not stage source/test dirty files.
- Do not stage untracked files.
- Do not start BUG-002, HEALTH-001, DOCS-008, Quick Capture, or source/test cleanup work.
- Do not use `git add .` or broad staging commands.

Acceptance:

- `docs/TASKS.md` includes REPO-005 and REPO-006.
- Cached diff contains exactly `docs/TASKS.md`.
- No source/test dirty files are staged or committed.
- No untracked files are staged or committed.
- Commit message subject is:
  `docs: record REPO-005 audit task`

Validation:

```bash
git status --short
rg -n "REPO-005|REPO-006|Commit REPO-005 task bookkeeping" docs/TASKS.md
git diff --cached --name-only
git diff --cached --check
```

## ANALYSIS-JSON-001 - Validate JSON Repair Hardening

Status: DONE

Goal:

Validate and commit the existing JSON repair hardening for malformed model output that is missing commas between JSON members or values.

Problem:

The current dirty worktree includes a focused change in `block_analyze.py` that repairs missing commas and adds a regression test in `tests/test_block_analyze_json.py`. This should be validated and committed separately from queue, worker, rollup, Ollama, desktop, Health, and Quick Capture work.

Allowed files:

- `block_analyze.py`
- `tests/test_block_analyze_json.py`
- `docs/TASKS.md` only if marking this task DONE after commit

Scope:

- Inspect the existing changes in `block_analyze.py` and `tests/test_block_analyze_json.py`.
- Validate that the JSON repair behavior is coherent and covered by the focused test.
- Do not expand the implementation beyond JSON repair hardening.
- Do not touch API, service, storage, worker, Ollama, desktop, `.gitignore`, or unrelated test files.
- Do not start BUG-002, HEALTH-001, DOCS-008, Quick Capture, queue, worker, rollup, Ollama, or desktop tasks.
- Stage and commit only files in the allowed list.

Acceptance:

- Missing-comma JSON repair is covered by `tests/test_block_analyze_json.py`.
- Focused validation passes.
- Workflow-required validation passes.
- Cached diff contains only allowed files.
- No unrelated dirty or untracked files are staged or committed.
- Commit message subject is:
  `fix: harden JSON repair for missing commas`

Validation:

```bash
git status --short
git diff -- block_analyze.py tests/test_block_analyze_json.py
.venv/bin/python -m pytest -q tests/test_block_analyze_json.py
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
git diff --cached --name-only
git diff --cached --check
```

## REPO-007 - Register Remaining REPO-005 Follow-Up Tasks

Status: DONE

Goal:

Register the remaining follow-up tasks identified by the completed REPO-005 dirty-change audit so future runs do not need one registration round per task.

Problem:

REPO-005 identified several coherent dirty-worktree buckets after ANALYSIS-JSON-001 was completed by `e4d6b82 fix: harden JSON repair for missing commas`. The remaining buckets need explicit task entries before any source, test, queue, worker, rollup, Ollama, desktop, repo-cleanup, BUG-002, HEALTH-001, DOCS-008, or Quick Capture work begins.

Allowed files:

- `docs/TASKS.md`

Scope:

- Add only missing task entries for:
  - `ANALYSIS-QUEUE-001 - Validate enqueue-only analysis API path`
  - `WORKER-LEASE-001 - Validate worker lease and retry behavior`
  - `ROLLUP-001 - Validate entry version, rollup, and memory idempotency`
  - `OLLAMA-001 - Decide Ollama autostart behavior`
  - `DESKTOP-001 - Decide whether desktop_app.py belongs in this baseline`
  - `REPO-008 - Decide .omx ignore policy`
- Do not register `ANALYSIS-JSON-001`; it is already DONE.
- Do not modify application code.
- Do not modify tests.
- Do not modify untracked files.
- Do not modify `.gitignore`.
- Do not start implementation, cleanup, BUG-002, HEALTH-001, DOCS-008, Quick Capture, queue, worker, rollup, Ollama, desktop, or repo-cleanup tasks.
- Do not stage or commit unless explicitly requested by the prompt executing this task.

Acceptance:

- All six remaining REPO-005 follow-up task IDs are present exactly once.
- `ANALYSIS-JSON-001` remains DONE and is not duplicated.
- No files outside `docs/TASKS.md` are changed by this task.
- No source, test, untracked, desktop, Ollama, storage, service, worker, API, or `.gitignore` files are touched.
- Nothing is staged or committed unless the executing prompt explicitly requires a docs-only commit.

Validation:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
rg -n "ANALYSIS-QUEUE-001|WORKER-LEASE-001|ROLLUP-001|OLLAMA-001|DESKTOP-001|REPO-008|ANALYSIS-JSON-001" docs/TASKS.md
```

## ANALYSIS-QUEUE-001 - Validate enqueue-only analysis API path

Status: DONE

Goal:

Validate and commit the existing enqueue-only analysis API path without mixing it with worker, rollup, Ollama, desktop, repo-cleanup, Health, or Quick Capture work.

Problem:

REPO-005 identified dirty analysis API and service changes that appear to move analysis work onto the job queue instead of running it synchronously. This path must be validated as its own coherent task before broader feature work resumes.

Allowed files:

- `api/routes_meta.py`
- `services/analysis_jobs.py`
- `services/analysis_service.py`
- `tests/test_api_enqueue_behavior.py`
- `docs/TASKS.md` only if marking this task DONE after commit

Scope:

- Inspect the existing dirty changes for the enqueue-only API path.
- Preserve the backend API contract unless the task evidence proves a narrow correction is required.
- Do not touch worker lease, rollup, memory, Ollama, desktop, `.gitignore`, audio ingest, Health, Quick Capture, or unrelated tests.
- Stage and commit only files in the allowed list if the validation succeeds.

Acceptance:

- The API path enqueues analysis work instead of running model analysis synchronously.
- Regression coverage proves the enqueue behavior.
- Workflow-required validation passes.
- Cached diff contains only allowed files.
- No unrelated dirty or untracked files are staged or committed.

Validation:

```bash
git status --short
git diff -- api/routes_meta.py services/analysis_jobs.py services/analysis_service.py tests/test_api_enqueue_behavior.py
.venv/bin/python -m pytest -q tests/test_api_enqueue_behavior.py
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
git diff --cached --name-only
git diff --cached --check
```

## WORKER-LEASE-001 - Validate worker lease and retry behavior

Status: DONE

Goal:

Validate and commit the existing worker lease, retry, and failure-handling changes without mixing them with API enqueue, rollup, Ollama, desktop, repo-cleanup, Health, or Quick Capture work.

Problem:

REPO-005 identified dirty queue and worker changes plus worker-focused tests. These appear to improve job claiming, leases, retries, and error handling, and need their own focused validation before future queue or worker edits begin.

Allowed files:

- `storage/repo_jobs.py`
- `services/analysis_jobs.py`
- `workers/analysis_worker.py`
- `tests/test_repo_jobs_claim.py`
- `tests/conftest.py`
- `tests/test_analysis_worker_errors.py`
- `docs/TASKS.md` only if marking this task DONE after commit

Scope:

- Inspect the existing dirty worker lease and retry changes.
- Keep behavior focused on queue claiming, lease expiry, retry, and error handling.
- Do not touch API enqueue, rollup, memory, Ollama, desktop, `.gitignore`, audio ingest, Health, Quick Capture, or unrelated tests.
- Stage and commit only files in the allowed list if the validation succeeds.

Acceptance:

- Job claiming and lease behavior are covered by regression tests.
- Worker error and retry behavior are covered by regression tests.
- Workflow-required validation passes.
- Cached diff contains only allowed files.
- No unrelated dirty or untracked files are staged or committed.

Validation:

```bash
git status --short
git diff -- storage/repo_jobs.py services/analysis_jobs.py workers/analysis_worker.py tests/test_repo_jobs_claim.py tests/conftest.py tests/test_analysis_worker_errors.py
.venv/bin/python -m pytest -q tests/test_repo_jobs_claim.py tests/test_analysis_worker_errors.py
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
git diff --cached --name-only
git diff --cached --check
```

## ROLLUP-001 - Validate entry version, rollup, and memory idempotency

Status: DONE

Goal:

Validate and commit the existing entry update, rollup stale-protection, audio reanalysis, and memory idempotency changes without mixing them with queue, worker, Ollama, desktop, repo-cleanup, Health, or Quick Capture work.

Problem:

REPO-005 identified dirty storage, runner, audio reanalysis, and rollup-related tests. These changes appear to protect analysis results against stale entry versions and make rollup or memory updates idempotent.

Allowed files:

- `services/analysis_runner.py`
- `services/audio_ingest_service.py`
- `storage/repo_entries.py`
- `storage/repo_jobs.py`
- `workers/analysis_worker.py`
- `tests/conftest.py`
- `tests/test_audio_reanalyze.py`
- `tests/test_entry_update_flow.py`
- `tests/test_memory_update_idempotency.py`
- `tests/test_rollup_stale_protection.py`
- `docs/TASKS.md` only if marking this task DONE after commit

Scope:

- Inspect the existing dirty rollup, stale-protection, and memory-idempotency changes.
- Keep optional audio behavior from becoming required for the text diary core.
- Do not touch API enqueue, Ollama, desktop, `.gitignore`, Health, Quick Capture, or unrelated tests.
- Stage and commit only files in the allowed list if the validation succeeds.

Acceptance:

- Entry-version stale protection is covered by regression tests.
- Rollup or memory idempotency behavior is covered by regression tests.
- Text diary core remains usable without audio-heavy dependencies.
- Workflow-required validation passes.
- Cached diff contains only allowed files.
- No unrelated dirty or untracked files are staged or committed.

Validation:

```bash
git status --short
git diff -- services/analysis_runner.py services/audio_ingest_service.py storage/repo_entries.py storage/repo_jobs.py workers/analysis_worker.py tests/conftest.py tests/test_audio_reanalyze.py tests/test_entry_update_flow.py tests/test_memory_update_idempotency.py tests/test_rollup_stale_protection.py
.venv/bin/python -m pytest -q tests/test_audio_reanalyze.py tests/test_entry_update_flow.py tests/test_memory_update_idempotency.py tests/test_rollup_stale_protection.py
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
git diff --cached --name-only
git diff --cached --check
```

## OLLAMA-001 - Decide Ollama autostart behavior

Status: DONE

Goal:

Decide whether the existing Ollama client autostart behavior belongs in this baseline, then either commit it as a focused change or record the decision not to keep it.

Problem:

REPO-005 identified dirty Ollama client changes and a focused Ollama test. Autostart behavior affects local runtime expectations and should not be mixed with API, worker, rollup, desktop, Health, or Quick Capture work.

Allowed files:

- `llm/ollama_client.py`
- `tests/test_ollama_client.py`
- `docs/TASKS.md` only if marking this task DONE after commit or recording WONTFIX

Scope:

- Inspect the existing Ollama client changes and test.
- Decide whether autostart should be part of the current local-first baseline.
- If keeping it, validate and commit only the allowed files.
- If rejecting it, record WONTFIX or a follow-up cleanup task without reverting unrelated work.
- Do not touch API, services, storage, workers, desktop, `.gitignore`, Health, Quick Capture, or unrelated tests.

Acceptance:

- The Ollama autostart decision is explicit.
- If kept, focused tests cover the behavior and validation passes.
- If rejected, the task records the reason and no implementation work is committed.
- Cached diff contains only allowed files if a commit is made.
- No unrelated dirty or untracked files are staged or committed.

Validation:

```bash
git status --short
git diff -- llm/ollama_client.py tests/test_ollama_client.py docs/TASKS.md
.venv/bin/python -m pytest -q tests/test_ollama_client.py
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
git diff --cached --name-only
git diff --cached --check
```

## WORKER-LOOP-001 - Decide analysis worker loop mode behavior

Status: DONE

Goal:

Decide whether the remaining dirty `workers/analysis_worker.py` loop-mode behavior should be committed as part of the analysis worker baseline.

Problem:

After OLLAMA-001, the remaining `workers/analysis_worker.py` diff appears to add long-running worker loop behavior. This must be handled separately from Ollama readiness, worker lease/retry behavior, desktop launcher behavior, repo ignore policy, Health, Quick Capture, queue, or rollup work.

Allowed files:

- `workers/analysis_worker.py`
- `tests/test_analysis_worker_loop.py` only if focused loop-mode regression coverage is required
- `docs/TASKS.md` only if marking this task DONE, BLOCKED, or WONTFIX after validation

Scope:

- Inspect the remaining loop-mode diff in `workers/analysis_worker.py`.
- Decide whether loop mode belongs in the committed analysis worker behavior.
- If keeping it, ensure loop mode is explicit opt-in behavior and does not change the default one-shot worker behavior.
- If rejecting it, remove the loop-mode dirty diff or record WONTFIX without touching unrelated files.
- Keep this task separate from Ollama readiness, lease/retry behavior, desktop launcher behavior, `.gitignore`, Health, Quick Capture, queue, and rollup work.
- Stage and commit only files in the allowed list if the decision is implemented successfully.

Acceptance:

- The loop-mode decision is explicit.
- Default worker execution remains one-shot unless loop mode is explicitly requested.
- If kept, focused regression coverage validates loop-mode behavior without relying on an infinite test run.
- If rejected, the loop-mode dirty diff is removed or the rejection is recorded without mixing unrelated work.
- Workflow-required validation passes.
- Cached diff contains only allowed files if a commit is made.
- `.gitignore`, `desktop_app.py`, Ollama files, API files, service files, storage files, and unrelated tests are not staged or committed.

Validation:

```bash
git status --short
git diff -- workers/analysis_worker.py tests/test_analysis_worker_loop.py docs/TASKS.md
.venv/bin/python -m pytest -q tests/test_analysis_worker_loop.py
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
git diff --cached --name-only
git diff --cached --check
```

## DESKTOP-001 - Decide whether desktop_app.py belongs in this baseline

Status: BLOCKED

Blocked reason:

- `desktop_app.py` imports `requests`, but `requests` is not declared in `requirements.txt` or `requirements-dev.txt`, and `.venv/bin/python -c "import desktop_app"` fails with `ModuleNotFoundError: No module named 'requests'`.

Goal:

Decide whether the untracked `desktop_app.py` belongs in this baseline, then either register a future implementation task or intentionally leave it out of the current baseline.

Problem:

REPO-005 identified `desktop_app.py` as an untracked desktop entry layer. Desktop remains optional and must not become a required dependency of the core text diary system, so this file needs an explicit baseline decision before desktop or Quick Capture work continues.

Allowed files:

- `docs/TASKS.md`
- `desktop_app.py` only if the executing prompt explicitly authorizes inspecting or staging the desktop baseline file

Scope:

- Decide whether `desktop_app.py` should be kept, deferred, or removed in a later explicit task.
- Do not implement desktop behavior.
- Do not make desktop dependencies required for the core text diary system.
- Do not touch API, services, storage, workers, Ollama, `.gitignore`, Health, Quick Capture, or tests.
- Do not stage or commit `desktop_app.py` unless the executing prompt explicitly requires a desktop baseline commit.

Acceptance:

- The baseline decision for `desktop_app.py` is explicit.
- If deferred, a future desktop task is registered instead of implemented.
- If kept, the allowed file scope and validation for the desktop baseline are explicit before any commit.
- No source, test, or untracked files are touched unless explicitly authorized by the executing prompt.

Validation:

```bash
git status --short
git diff -- docs/TASKS.md
git ls-files --others --exclude-standard desktop_app.py
git diff --cached --name-only
git diff --cached --check
```

## DESKTOP-002 - Remove blocked desktop launcher from worktree

Status: DONE

Goal:

Remove the untracked blocked `desktop_app.py` launcher from the worktree because it was not accepted into the baseline by `DESKTOP-001`.

Problem:

`DESKTOP-001` is blocked because `desktop_app.py` imports undeclared dependency `requests`. The untracked launcher should not remain as unresolved worktree state, and it should not be converted into desktop product work without a new accepted task.

Allowed files:

- `desktop_app.py`
- `docs/TASKS.md` only if marking this task DONE or BLOCKED after execution

Scope:

- Remove `desktop_app.py` from the worktree only because it is untracked, blocked, and not accepted into baseline.
- Do not add `requests`.
- Do not modify requirements files.
- Do not implement desktop launcher behavior.
- Do not convert this into Quick Capture, tray app, global hotkey, packaging, or desktop product work.
- Do not touch API, services, storage, workers, Ollama, tests, `.gitignore`, or any other files.

Acceptance:

- `desktop_app.py` no longer appears as an untracked worktree file.
- `DESKTOP-002` is marked DONE after removal.
- No files outside `desktop_app.py` and allowed task bookkeeping are changed.
- No desktop launcher implementation or dependency changes are introduced.

Validation:

```bash
git status --short
git ls-files --others --exclude-standard desktop_app.py
git diff -- docs/TASKS.md
git diff --cached --name-only
git diff --cached --check
```

## REPO-008 - Decide .omx ignore policy

Status: DONE

Goal:

Decide whether `.omx/` should be ignored in this repository and make only the minimal policy or task-queue update needed.

Problem:

REPO-005 identified `.gitignore` dirty state related to local OMX files. The repo needs an explicit policy decision before `.gitignore` is changed or committed, because local agent state should not be mixed with source, test, Health, Quick Capture, desktop, or runtime behavior work.

Allowed files:

- `.gitignore`
- `docs/TASKS.md` only if marking this task DONE after commit or recording the policy decision

Scope:

- Inspect the existing `.gitignore` change.
- Decide whether `.omx/` belongs in the repo ignore policy.
- If changing `.gitignore`, keep the edit minimal and commit only allowed files.
- Do not touch source files, tests, untracked files, desktop, Ollama, Health, Quick Capture, or implementation code.

Acceptance:

- The `.omx/` ignore policy decision is explicit.
- If `.gitignore` is changed, the diff is minimal and only policy-related.
- Cached diff contains only allowed files if a commit is made.
- No source, test, or untracked files are staged or committed.

Validation:

```bash
git status --short
git diff -- .gitignore docs/TASKS.md
git diff --cached --name-only
git diff --cached --check
```

## REPO-009 - Diagnose pytest startup and pre-push validation environment

Status: DONE

Completed evidence:

- Read-only diagnosis found the active pre-push hook comes from global `core.hooksPath` at `/Users/lincma/.codex/git-hooks/pre-push`.
- The hook runs plain `pytest -q`, which resolves to global Python 3.13 and fails outside the project environment.
- `.venv/bin/python -m pytest -q` completed with 43 passed and 2 warnings in 117.71s.
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` completed with 43 passed and 2 warnings in 1.59s and is hook-compatible without editing or bypassing the hook.
- No project source, tests, requirements, global hook files, or global config were modified.

Goal:

Diagnose why the canonical project validation command now hangs and determine the safe path for pushing the existing local `HEALTH-001` commit without bypassing hooks blindly.

Problem:

The local branch is ahead of `origin/main` by `c80908a feat: expose core diagnostics without loading optional audio`, but `git push origin main` is blocked by the configured global pre-push hook. A read-only diagnosis found that the active hook comes from `/Users/lincma/.codex/git-hooks/pre-push`, runs plain `pytest -q`, resolves to a global Python 3.13 pytest, and fails with `ModuleNotFoundError: No module named 'storage'`. The canonical `.venv/bin/python -m pytest -q` command and `PYTHONPATH=. .venv/bin/python -m pytest -q` currently hang during pytest startup/import.

Allowed files:

- `docs/TASKS.md` only if marking this task DONE, BLOCKED, or recording a follow-up task
- `docs/PROJECT_STATE.md` only if recording a stable validation-environment fact or risk
- `docs/operations.md` only if documenting the accepted local validation or push procedure
- `pytest.ini` or `pyproject.toml` only if diagnosis proves a minimal pytest configuration fix is the required repo-side correction

Scope:

- Inspect pytest configuration files if present.
- Inspect `requirements.txt` and `requirements-dev.txt`.
- Inspect import-time side effects in `tests/conftest.py` and focused health tests.
- Check pytest plugin autoload behavior.
- Compare:
  - `.venv/bin/python -m pytest -q`
  - `PYTHONPATH=. .venv/bin/python -m pytest -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q`
  - focused health test command if useful
- Inspect the configured global pre-push hook read-only.
- Do not edit global hook files.
- Do not push.
- Do not bypass hooks.
- Do not start BUG-002, Quick Capture, DOCS-008, or implementation work.
- Do not modify source or test code unless a minimal validation-config fix is explicitly proven and limited to the allowed config files.

Acceptance:

- Identifies whether the `.venv` pytest hang is caused by project code/config, pytest/plugin behavior, local virtualenv state, or the global hook environment.
- Identifies whether plain hook `pytest -q` is unsafe because it uses global Python instead of the project virtualenv.
- Reports whether manual canonical validation can pass.
- Reports whether a controlled hook-bypass push would be safe, or why it is blocked.
- Records any required follow-up task instead of broadening into unrelated implementation work.
- Cached diff contains only allowed files if a commit is made.
- No global hook files, source files, test files, unrelated docs, or untracked files are modified, staged, committed, pushed, or deleted.

Validation:

```bash
git status --short --branch
git diff --cached --name-only
git diff --cached --check
git diff --check
```

## REPO-010 - Stabilize pytest cache behavior for validation

Status: DONE

Completed evidence:

- Added `pytest.ini` with `addopts = -p no:cacheprovider`.
- `.venv/bin/python -m pytest -q` completed with 45 passed in 1.52s.
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` completed with 45 passed in 1.34s.
- Explicit no-cache comparison completed with 45 passed in 1.37s.
- No source files, tests, global hook files, or global git config were modified.

Goal:

Make project pytest validation stable without requiring every run to remember an
ad-hoc `PYTEST_ADDOPTS="-p no:cacheprovider"` environment override.

Problem:

After `BUG-002` was completed and pushed, read-only push-block diagnosis found
that the full test suite passes but normal pytest can hang in this local repo
environment because of pytest cache provider or session cache behavior.

Observed validation evidence:

- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` timed out.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` did not resolve the timeout by itself.
- `.venv/bin/python -m pytest -q` timed out.
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. PYTEST_ADDOPTS="-p no:cacheprovider" pytest -q`
  completed with 45 passed in 1.50s.

Allowed files:

- `pytest.ini` if creating a pytest configuration file is the minimal stable fix
- `pyproject.toml` or an equivalent existing pytest configuration file if one
  already owns pytest configuration
- `docs/WORKFLOW.md` only if canonical validation commands must be updated
- `AGENTS.md` only if required validation commands must be updated
- `docs/TASKS.md` for task status bookkeeping
- `docs/PROJECT_STATE.md` only if recording stable validation facts or risks

Scope:

- Configure project pytest so the canonical full-suite validation avoids the
  cache-provider hang.
- Keep the full test suite running; do not skip, deselect, or weaken tests.
- Preserve push-compatible validation with project `.venv` and `PYTHONPATH=.`.
- Do not modify application source files.
- Do not modify tests unless a validation-only fixture/config change is proven
  necessary and kept inside this task.
- Do not modify global hook files or global git config.
- Do not push.
- Do not start Quick Capture, DOCS-008, HEALTH-002, BUG-002, or unrelated work.

Acceptance:

- `.venv/bin/python -m pytest -q` completes without hanging and runs the full
  suite.
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` completes without hanging
  and runs the full suite.
- The full suite still reports all tests passing.
- Push-compatible validation remains possible without editing or bypassing the
  global hook.
- No source files, unrelated tests, global hook files, global config, or
  unrelated docs are modified.

Validation:

```bash
.venv/bin/python -m pytest -q
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. PYTEST_ADDOPTS="-p no:cacheprovider" pytest -q
git diff --check
git diff --cached --name-only
git diff --cached --check
```

Suggested commit message if executing:

`test: disable pytest cache provider for stable validation`

Stop conditions:

- Stop if stable pytest behavior requires source behavior changes.
- Stop if the only viable fix requires modifying global hook files or global git
  config.
- Stop if validation requires skipping or weakening tests.
- Stop if the fix requires broader test infrastructure changes than pytest
  cache behavior.
- Record any broader issue as a separate task instead of expanding this task.

## REPO-011 - Remove stale desktop_app.py from compileall validation

Status: DONE

Completed evidence:

- Removed the stale `desktop_app.py` target from current canonical compileall
  validation commands in `AGENTS.md` and `docs/WORKFLOW.md`.
- Updated `docs/PROJECT_STATE.md` with the clean compileall validation fact.
- `.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py`
  passed without printing `Can't list 'desktop_app.py'`.
- `.venv/bin/python -m pytest -q` completed with 45 passed in 1.51s.

Depends on:

- `DESKTOP-002`
- `REPO-010`

Dependency status:

- Satisfied: `DESKTOP-002` removed the blocked optional desktop launcher from the worktree.
- Satisfied: `REPO-010` stabilized pytest cache behavior for validation.

Goal:

Remove the stale `desktop_app.py` target from current canonical compileall
validation commands now that the optional launcher is absent.

Problem:

`desktop_app.py` was removed by `DESKTOP-002`, but current validation command
references can still include it. `compileall` exits successfully but prints
`Can't list 'desktop_app.py'`, making otherwise clean validation look noisy.

Allowed files:

- `AGENTS.md` only if it contains the current canonical compileall validation command
- `docs/WORKFLOW.md` only if it contains the current canonical compileall validation command
- `docs/PROJECT_STATE.md` only if recording the updated validation fact is required
- `docs/TASKS.md` for task status bookkeeping or current non-historical validation command references
- Config or script files only if they actually contain the current stale compileall validation command

Scope:

- Find all references to `desktop_app.py`.
- Remove `desktop_app.py` only from stale current validation or compileall command references.
- Preserve the rest of each validation command.
- Preserve historical notes and completed-task evidence unless the executing prompt explicitly allows updating a current validation command there.
- Do not modify application source files.
- Do not modify tests unless a validation-only update is explicitly required and remains inside this task.
- Do not restore `desktop_app.py`.
- Do not start Quick Capture, DOCS-008, HEALTH-002, or unrelated implementation work.
- Do not push.

Acceptance:

- Current canonical compileall validation no longer references `desktop_app.py`.
- Historical notes are not broadly rewritten or removed.
- Compileall validation runs without printing `Can't list 'desktop_app.py'`.
- No application source files are modified.
- No tests are modified unless explicitly required by a validation-only update.
- Cached diff contains only files allowed by this task if a commit is made.

Validation:

```bash
rg -n "desktop_app.py|compileall" .
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py
.venv/bin/python -m pytest -q
git diff --check
git diff --cached --name-only
git diff --cached --check
```

Suggested commit message if executing:

`chore: remove stale desktop compileall target`

Stop conditions:

- Stop if removing the stale reference requires modifying application source files.
- Stop if validation requires restoring `desktop_app.py`.
- Stop if the needed edit is outside documentation, configuration, or script validation surfaces.
- Stop if broad historical cleanup would be required; record that as a separate task instead.

## REPO-012 - Reconcile stale task queue statuses after cleanup

Status: DONE

Completed evidence:

- Reconciled stale status rows for `DOCS-002`, `REPO-001`, `REPO-002`,
  `REPO-003`, and `HEALTH-001` using committed evidence only.
- Updated `DOCS-008` dependency status so the stale `REPO-002` blocker no
  longer blocks a future selected `DOCS-008` run.
- Updated `HEALTH-002` dependency status while keeping it blocked because its
  executable task contract still lacks allowed files and validation.
- Did not execute `DOCS-008`, `HEALTH-002`, Quick Capture, or implementation
  work.

Goal:

Reconcile stale `docs/TASKS.md` statuses, dependency notes, and blocker notes
after the repository cleanup, Health API, FastAPI lifecycle, pytest stability,
and compileall cleanup work has been completed and pushed.

Problem:

A read-only task inventory after `REPO-011` found several task rows whose
statuses or blockers appear stale compared with existing committed evidence.
The queue should be reconciled before starting `DOCS-008`, `HEALTH-002`, Quick
Capture, or new implementation work.

Allowed files:

- `docs/TASKS.md`
- `docs/PROJECT_STATE.md` only if the workflow requires recording current
  project facts

Scope:

- Use existing committed evidence only; do not invent completion evidence.
- Reconcile stale statuses or completion evidence for:
  - `DOCS-002`
  - `REPO-001`
  - `REPO-002`
  - `REPO-003`
  - `HEALTH-001`
- Reconcile dependency or blocker notes for:
  - `DOCS-008`
  - `HEALTH-002`
- If evidence proves a task is complete, mark it DONE and reference the commit
  or evidence.
- If evidence is insufficient, keep the task open or blocked and record what is
  missing.
- If a blocker is stale because its dependency is now done, update only the
  blocker or dependency note; do not execute the blocked task.
- Do not modify source files.
- Do not modify tests.
- Do not start `DOCS-008`, `HEALTH-002`, Quick Capture, or implementation work.
- Do not push.

Acceptance:

- `DOCS-002`, `REPO-001`, `REPO-002`, `REPO-003`, and `HEALTH-001` each have a
  current status supported by recorded committed evidence or an explicit note
  explaining what evidence is missing.
- `DOCS-008` blocker/dependency notes reflect whether `REPO-002` is still a real
  blocker.
- `HEALTH-002` blocker/dependency notes reflect whether `HEALTH-001` is still a
  real blocker.
- No task implementation work is started.
- No source or test files are changed.
- Cached diff contains only allowed docs files if a commit is made.

Validation:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
rg -n "(DOCS-002|REPO-001|REPO-002|REPO-003|HEALTH-001|HEALTH-002|DOCS-008|REPO-012)" docs/TASKS.md docs/PROJECT_STATE.md
```

Suggested commit message if executing:

`docs: reconcile stale task queue statuses`

Stop conditions:

- Stop if reconciliation would require inspecting or modifying source/test
  behavior beyond committed evidence.
- Stop if a status cannot be changed without inventing completion evidence.
- Stop if updating `docs/PROJECT_STATE.md` would introduce wishlist or
  non-current facts.
- Record any broader cleanup or implementation need as a separate task instead
  of expanding this reconciliation.

## REPO-013 - Normalize validation entrypoint and hook-safe pytest command

Status: DONE

Completed evidence:

- Added `scripts/validate.sh` as the repo-local validation entrypoint.
- Documented `scripts/validate.sh` and the hook-safe
  `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` command.
- Documented the distinction between wrong-environment bare `pytest` failures
  and optional native dependency cold-start delays.
- `scripts/validate.sh` completed with pytest passing and compileall passing.
- `.venv/bin/python -m pytest -q` completed with 48 passed in 1.53s.
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` completed with 48 passed
  in 1.53s.
- `.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py`
  passed.
- No application source files, tests, global hook files, or global git config
  were modified.

Goal:

Make local validation entrypoints explicit and repeatable so contributors do not
accidentally run the system or global `pytest` environment instead of the
project `.venv`.

Problem:

The canonical project command `.venv/bin/python -m pytest -q` can pass, but the
configured global pre-push hook runs plain `pytest -q`. In this checkout, plain
`pytest` resolves outside the project `.venv` and can fail before tests run with
`ModuleNotFoundError: No module named 'storage'`. The audio feature test can also
look like pytest is stuck during a cold start because importing native optional
audio dependencies may be slow before the environment is warm.

Allowed files:

- `scripts/validate.sh` if adding a repo-local validation wrapper
- `README.md` only if documenting the accepted local validation command
- `docs/WORKFLOW.md` only if updating canonical validation workflow text
- `docs/PROJECT_STATE.md` only if recording stable current validation facts or
  risks
- `docs/TASKS.md` for task status bookkeeping

Scope:

- Add or update a repo-local validation wrapper that runs from the repository
  root using project `.venv` and `PYTHONPATH=.`.
- Keep canonical backend/frontend validation equivalent to:
  - `.venv/bin/python -m pytest -q`
  - `.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py`
- Document that contributors should not use bare `pytest -q` in this repo unless
  `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=.` is set.
- Mention the optional audio/native dependency cold-start behavior only as a
  local validation risk; do not weaken or skip audio tests.
- Do not modify application source files.
- Do not modify tests.
- Do not modify global hook files or global git config.
- Do not push.
- Do not start `HEALTH-002`, Quick Capture, desktop, audio behavior changes, or
  unrelated implementation work.

Acceptance:

- A single repo-local validation entrypoint exists or existing docs clearly name
  the canonical entrypoint.
- Hook-safe validation is documented as:
  `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q`.
- Documentation distinguishes the wrong-environment failure from slow optional
  native dependency cold starts.
- Full pytest and compileall validation pass through the accepted project
  environment.
- No application source files, tests, global hook files, or global git config are
  modified.
- Cached diff contains only files allowed by this task if a commit is made.

Validation:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
.venv/bin/python -m pytest -q
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py
```

Suggested commit message if executing:

`chore: normalize project validation entrypoint`

Stop conditions:

- Stop if stabilizing validation requires application source changes.
- Stop if the only viable fix requires modifying global hook files or global git
  config.
- Stop if validation requires skipping, deselecting, or weakening tests.
- Stop if the task would broaden into audio implementation changes, frontend
  health panel work, Quick Capture, desktop, or push-only publication.

## BUG-002 - Replace deprecated FastAPI on_event usage

Status: DONE

Completed evidence:

- `server.py` now uses FastAPI lifespan startup instead of deprecated `@app.on_event("startup")`.
- Focused lifespan tests cover database initialization and ingest-unavailable startup logging.
- Import-boundary, health, route behavior, full pytest, and compileall validation passed.

Scoped by:

- `BUG-002-SCOPE`

Problem:

FastAPI `0.123.1` emits a deprecation warning for `server.py` using `@app.on_event("startup")`.
Read-only scope discovery found:

- `server.py` is the only FastAPI app setup file: `app = FastAPI(title="Personal Diary AI & English Learning")`.
- `server.py` is the only file with lifecycle usage: `@app.on_event("startup")`.
- No `.on_event(` calls and no shutdown behavior were found.
- Startup behavior currently calls `init_db()` and logs an error when `app.state.ingest_entry` is unavailable.
- Existing `TestClient(server.app)` tests cover health, save/enqueue routes, fake-provider E2E, extreme input limits, and voice upload limits.
- Existing import-boundary tests verify importing `api.routes_diary` and `server` does not load audio-heavy modules.

Goal:

Replace deprecated FastAPI startup-event registration with FastAPI lifespan startup while preserving API behavior, startup behavior, optional-module boundaries, and the core diary chain.

Allowed files:

- `server.py`
- `tests/test_server_lifespan.py`
- `tests/test_import_boundaries.py` only if import-boundary assertions need focused extension
- `docs/TASKS.md` only if marking this task DONE or BLOCKED after execution
- `docs/PROJECT_STATE.md` only if recording removal of the stable FastAPI `on_event` risk after successful validation

Scope:

- Replace `server.py` `@app.on_event("startup")` with a FastAPI lifespan context.
- Preserve the existing `init_db()` startup call.
- Preserve the existing ingest-unavailable error log behavior.
- Preserve existing `app.state` setup, router registration, static-file behavior, and `uvicorn.run("server:app", ...)` behavior.
- Do not add shutdown side effects unless they are required by the lifespan context and remain no-op.
- Do not change API URLs, request/response payloads, database schema, migrations, upload/file behavior, audio behavior, desktop behavior, Quick Capture behavior, or frontend behavior.
- Do not import audio-heavy modules from `server` or `api.routes_diary`.

Acceptance:

- No `@app.on_event` or `.on_event(` usage remains in `server.py`.
- `server.py` uses FastAPI lifespan startup.
- `TestClient(server.app)` startup still initializes the database through `init_db()`.
- Existing ingest-unavailable startup logging behavior is preserved.
- Existing route behavior remains covered by focused and full tests.
- Import-boundary validation still proves `api.routes_diary` and `server` do not load `pipeline.audio_features`, `services.audio_ingest_service`, `numpy`, `faster_whisper`, or ffmpeg-dependent code.
- No source, test, or docs files outside the allowed list are changed.

Validation:

```bash
rg -n "@app\.on_event|\.on_event\(" server.py api tests
.venv/bin/python -m pytest -q tests/test_server_lifespan.py tests/test_import_boundaries.py tests/test_health.py
.venv/bin/python -m pytest -q tests/test_fake_provider_e2e.py tests/test_extreme_inputs.py tests/test_api_enqueue_behavior.py tests/test_voice_chat_upload_limit.py
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
git diff --check
git diff --cached --name-only
git diff --cached --check
```

Stop conditions:

- Stop if replacing the lifecycle hook requires changing files outside the allowed list.
- Stop if preserving startup behavior requires API contract changes, schema/migration changes, route rewrites, or optional audio/desktop/Quick Capture changes.
- Stop if import-boundary validation shows the lifecycle change loads audio-heavy modules from text-diary imports.
- Stop if validation requires modifying unrelated tests or source files.
- Record any new issue as a separate task instead of broadening this task.

## BUG-002-SCOPE - Discover FastAPI lifecycle replacement scope

Status: DONE

Completed findings:

- `server.py` is the only FastAPI app setup file and creates `app = FastAPI(title="Personal Diary AI & English Learning")`.
- The only deprecated lifecycle usage is `server.py` `@app.on_event("startup")`; no `.on_event(` calls were found.
- Startup behavior to preserve is `init_db()` plus the ingest-unavailable error log.
- No shutdown behavior exists.
- FastAPI is pinned to `0.123.1`, and the replacement should use FastAPI lifespan.
- Existing route/import coverage includes `tests/test_health.py`, `tests/test_import_boundaries.py`, `tests/test_fake_provider_e2e.py`, `tests/test_extreme_inputs.py`, `tests/test_api_enqueue_behavior.py`, and `tests/test_voice_chat_upload_limit.py`.
- `BUG-002` now has executable allowed files, acceptance criteria, validation, and stop conditions.

Goal:

Find enough information to turn `BUG-002` into an executable task contract without implementing the FastAPI lifecycle replacement.

Allowed files:

- `docs/TASKS.md` for recording findings, updating `BUG-002-SCOPE`, and updating the `BUG-002` task contract if enough scope is discovered
- `docs/PROJECT_STATE.md` only if the workflow requires recording stable current project facts

Scope:

- Read-only source and test inspection.
- Inspect all FastAPI app setup files.
- Inspect all `@app.on_event` or `.on_event(` usages.
- Inspect startup and shutdown behavior.
- Inspect tests that cover server startup, health, routes, app import, and optional-heavy imports.
- Inspect FastAPI version and dependency constraints in requirements files.
- Do not implement `BUG-002`.
- Do not modify source files or test files.
- Do not push.
- Do not start Quick Capture, DOCS-008, HEALTH-002, or unrelated work.

Expected findings:

- Exact files containing deprecated `on_event` usage.
- Whether replacement should use FastAPI lifespan.
- Allowed implementation files for `BUG-002`.
- Required tests or new focused tests.
- Acceptance criteria.
- Validation commands.
- Stop or block conditions.
- Risks around optional audio imports or runtime side effects.

Acceptance:

- If enough scope is discovered, update `BUG-002` from BLOCKED to executable status according to the workflow, including allowed files, acceptance criteria, validation, and stop conditions.
- If enough scope is not discovered, leave `BUG-002` blocked and record exactly what is missing.
- `BUG-002-SCOPE` records the discovery findings and final status.
- No source files, test files, unrelated docs, hook files, or global config are modified, staged, committed, pushed, or deleted.

Validation:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
```

Suggested commit message if executing and updating docs:

`docs: scope fastapi lifecycle replacement`

Stop conditions:

- Stop after registering this task if it did not already exist.
- Stop if inspection shows implementation is required to answer the scope question.
- Stop if scope discovery would require source or test edits.
- Stop if the findings require a broader architectural decision than replacing deprecated FastAPI lifecycle registration.

## HEALTH-001 - Core Health / Diagnostics API

Status: DONE

Completed evidence:

- Completed by `c80908a feat: expose core diagnostics without loading optional
  audio`, which added `api/routes_health.py`, wired it in `server.py`, added
  `tests/test_health.py`, and updated `docs/PROJECT_STATE.md`.
- Commit evidence records `.venv/bin/python -m pytest -q` passing with 43
  passed and 2 warnings, plus compileall exiting successfully with the then
  absent optional `desktop_app.py` note.

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

## HEALTH-002-SCOPE - Define health diagnostics panel task contract

Status: DONE

Completed evidence:

- Defined `HEALTH-002` as frontend-only UI/API integration work against an
  existing health endpoint.
- Recorded exact allowed files, acceptance criteria, validation commands,
  dependency notes, and stop conditions for `HEALTH-002`.
- Endpoint details from this pass were later corrected by
  `HEALTH-002-CONTRACT-FIX`: source and tests identify the diagnostics endpoint
  as `GET /api/health`; `GET /health` is only the simple meta health endpoint.
- Updated `HEALTH-002` from `BLOCKED` to `READY` without implementing it.
- Did not modify source files, test files, Quick Capture, `QC-*`, or
  `DESKTOP-001`.

Goal:

Define `HEALTH-002` as an exact executable task contract using only committed
facts and docs. Do not implement `HEALTH-002` in this task.

Allowed files:

- `docs/TASKS.md`
- `docs/PROJECT_STATE.md` only if the workflow requires recording current
  project facts

Scope:

- Define whether `HEALTH-002` is backend-only, frontend-only, or UI/API
  integration work.
- Define exact allowed files for `HEALTH-002`.
- Define acceptance criteria for the health diagnostics panel.
- Define validation commands for `HEALTH-002`.
- Define stop or block conditions for `HEALTH-002`.
- Record dependency notes using existing committed facts only.
- Record whether `HEALTH-002` must consume the existing `/api/health` endpoint
  from `HEALTH-001`.
- Record how `HEALTH-002` must avoid optional audio-heavy imports and unrelated
  feature work.
- Do not modify source files.
- Do not modify test files.
- Do not start `HEALTH-002`.
- Do not start Quick Capture or any `QC-*` task.
- Do not modify `DESKTOP-001`.
- Do not push.

Acceptance:

- `HEALTH-002-SCOPE` is present in `docs/TASKS.md` with status `DONE`.
- The future `HEALTH-002` task contract has status, purpose, exact allowed
  files/scope, acceptance criteria, validation commands, stop/block conditions,
  and dependency notes.
- The contract records whether `HEALTH-002` is backend-only, frontend-only, or
  UI/API integration work.
- The contract records whether `HEALTH-002` must consume the existing
  `/api/health` endpoint from `HEALTH-001`.
- The contract records how `HEALTH-002` must avoid optional audio-heavy imports
  and unrelated feature work.
- If existing docs are insufficient to define the contract, `HEALTH-002` remains
  blocked and the missing information is recorded exactly.
- If existing docs are sufficient, `HEALTH-002` is updated from `BLOCKED` to
  `READY`.
- No source or test files are changed.

Validation:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
rg -n "(HEALTH-002|HEALTH-002-SCOPE|QC-001|DOCS-008|/api/health|health)" docs/TASKS.md docs/PROJECT_STATE.md docs/WORKFLOW.md AGENTS.md
```

Suggested commit message if executing:

`docs: define health diagnostics task contract`

Stop conditions:

- Stop after registering this task if it did not already exist.
- Stop if defining the `HEALTH-002` contract would require source or test
  inspection beyond committed docs.
- Stop if the docs do not contain enough information to define the executable
  contract.
- Stop if the work would broaden into implementing `HEALTH-002`, Quick Capture,
  any `QC-*` task, or `DESKTOP-001`.

## HEALTH-002-CONTRACT-FIX - Correct health diagnostics panel task contract

Status: DONE

Completed evidence:

- Corrected `HEALTH-002` to consume the existing diagnostics endpoint
  `GET /api/health`.
- Kept `GET /health` only as the simple meta health endpoint distinction.
- Moved the long `HEALTH-002` executable contract into
  `docs/tasks/HEALTH-002.md`.
- Kept the `HEALTH-002` row in this file as an index entry with a capsule link.
- Replaced the broad "fail on any innerHTML" validation with health-panel safety
  validation that does not fail on existing frontend baseline usage.
- Did not modify source files, test files, `README.md`, `docs/operations.md`,
  Quick Capture, any `QC-*` task, or `DESKTOP-001`.

Goal:

Correct the docs-only `HEALTH-002` task contract after review found context
drift in the endpoint, task-capsule layout, and frontend validation wording.
Do not implement `HEALTH-002` in this task.

Problem:

The current `HEALTH-002` row says the panel should consume `GET /health`, but
the actual diagnostics route and tests use `GET /api/health`. The current row
also keeps a long executable contract in `docs/TASKS.md` after `DOCS-008`
introduced per-task capsules, and its validation command would fail on existing
frontend `innerHTML` usage instead of only guarding the health panel change.

Allowed files:

- `docs/TASKS.md`
- `docs/tasks/HEALTH-002.md`
- `docs/PROJECT_STATE.md` only if the workflow requires recording current
  project facts

Scope:

- Correct `HEALTH-002` to consume the existing diagnostics endpoint
  `GET /api/health`.
- Keep `GET /health` documented only as the simple meta health endpoint if it is
  mentioned at all.
- Move the detailed `HEALTH-002` executable contract into
  `docs/tasks/HEALTH-002.md`.
- Keep the `HEALTH-002` row in `docs/TASKS.md` as an index entry with status,
  dependency, short goal, and task-capsule link.
- Replace broad "fail on any innerHTML" validation with validation that does not
  fail on existing frontend baseline usage and still guards against unsafe
  health-panel rendering.
- Do not modify source files.
- Do not modify test files.
- Do not implement `HEALTH-002`.
- Do not start Quick Capture or any `QC-*` task.
- Do not modify `DESKTOP-001`.
- Do not push.

Acceptance:

- `HEALTH-002` remains or becomes `READY` only with the corrected
  `GET /api/health` endpoint.
- `docs/TASKS.md` no longer contains the full long-form `HEALTH-002` contract;
  it points to `docs/tasks/HEALTH-002.md`.
- `docs/tasks/HEALTH-002.md` contains the complete allowed files, scope,
  acceptance criteria, validation commands, stop conditions, and dependency
  notes.
- Validation wording no longer rejects all existing `innerHTML` usage in the
  frontend baseline.
- No source or test files are changed.

Validation:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
rg -n "(HEALTH-002|HEALTH-002-CONTRACT-FIX|/api/health|GET /health|docs/tasks/HEALTH-002.md|innerHTML)" docs/TASKS.md docs/tasks/HEALTH-002.md docs/PROJECT_STATE.md docs/WORKFLOW.md AGENTS.md
```

Suggested commit message if executing:

`docs: correct health diagnostics task contract`

Stop conditions:

- Stop after registering this task if it did not already exist.
- Stop if correcting the contract requires modifying source or test files.
- Stop if source and test evidence contradict the endpoint correction.
- Stop if the work would broaden into implementing `HEALTH-002`, Quick Capture,
  any `QC-*` task, or `DESKTOP-001`.

## HEALTH-002 - Core Health / Diagnostics Frontend Panel

Status: DONE

Task capsule:

- `docs/tasks/HEALTH-002.md`

Depends on:

- `HEALTH-001`

Dependency status:

- Satisfied by `c80908a feat: expose core diagnostics without loading optional
  audio`.
- Existing source and tests identify the diagnostics endpoint as
  `GET /api/health`.
- `GET /health` is the simple meta health endpoint, not the diagnostics panel
  data source.

Goal:

Add a small frontend diagnostics panel/page that displays the existing backend
health summary for local operational visibility.

Scope summary:

- Frontend-only UI/API integration.
- Consume the existing `GET /api/health` endpoint from `HEALTH-001`.
- Keep details, validation, and stop conditions in the task capsule.

Result: implemented by `67e3bba feat: make core diagnostics visible before
feature expansion`; status reconciled by `HEALTH-002-CLOSEOUT`.

## HEALTH-002-CLOSEOUT-CONTRACT-FIX - Correct health closeout scope

Status: DONE

Goal: repair the `HEALTH-002-CLOSEOUT` allowed-file scope so the closeout can
also update the legacy `docs/tasks/HEALTH-002.md` capsule status.

Task directory: `docs/tasks/HEALTH-002-CLOSEOUT-CONTRACT-FIX/`

Allowed files: `docs/TASKS.md`

Acceptance: update only the `HEALTH-002-CLOSEOUT` task contract in this index
so its allowed files include `docs/tasks/HEALTH-002.md`; do not execute
`HEALTH-002-CLOSEOUT`.

Result: `HEALTH-002-CLOSEOUT` now includes `docs/tasks/HEALTH-002.md` in its
allowed files so the next task can reconcile the legacy capsule status.

Validation: `git diff --check`; focused `rg` for
`HEALTH-002-CLOSEOUT-CONTRACT-FIX`, `HEALTH-002-CLOSEOUT`, and
`docs/tasks/HEALTH-002.md`; `git diff --cached --name-only`;
`git diff --cached --check`.

Stop: register only if missing; stop after fixing the contract in the next run.

## HEALTH-002-CLOSEOUT - Reconcile completed health panel task status

Status: DONE

Goal: close the stale `HEALTH-002` task status after the frontend diagnostics
panel was implemented in `67e3bba` and recorded in `docs/PROJECT_STATE.md`.

Task directory: `docs/tasks/HEALTH-002-CLOSEOUT/`

Key docs to create during execution:

- `docs/tasks/HEALTH-002-CLOSEOUT/001-contract.md`
- `docs/tasks/HEALTH-002-CLOSEOUT/002-validation.md`

Allowed files: `docs/TASKS.md`, `docs/tasks/HEALTH-002.md`,
`docs/tasks/HEALTH-002-CLOSEOUT/`

Acceptance: mark `HEALTH-002` as `DONE` using committed evidence only, preserve
its capsule link, record `67e3bba` as the implementation evidence, and avoid
source/test/frontend/runtime changes.

Result: `HEALTH-002` is marked `DONE` in both the task index and legacy capsule
using committed evidence from `67e3bba`.

Validation: `git diff --check`; focused `rg` for `HEALTH-002`,
`HEALTH-002-CLOSEOUT`, `67e3bba`, and `Status: DONE`; `git diff --cached
--name-only`; `git diff --cached --check`.

Stop: register only if missing; stop if source/test/runtime inspection or
changes become necessary beyond committed evidence.

## FILE-MGMT-001 - Define task directory file management model

Status: DONE

Goal: define a task-directory governance model so `docs/TASKS.md` becomes an
index and task details live in numbered files under `docs/tasks/<TASK_ID>/`.

Task directory: `docs/tasks/FILE-MGMT-001/`

Key docs to create during execution:

- `docs/tasks/FILE-MGMT-001/001-contract.md`
- `docs/tasks/FILE-MGMT-001/002-task-directory-model.md`
- `docs/tasks/FILE-MGMT-001/003-migration-checklist.md`
- `docs/tasks/FILE-MGMT-001/004-validation.md`

Allowed files: `AGENTS.md`, `docs/TASKS.md`, `docs/WORKFLOW.md`,
`docs/tasks/FILE-MGMT-001/`

Acceptance: define the index-vs-directory contract, numbered document categories
for docs/code-feature/optimization/validation/archive content, and split rules:
500 lines is the soft split trigger; 1000 lines is the hard limit for one task
document. Do not migrate historical tasks in this task.

Result: task-directory governance is defined in `AGENTS.md`,
`docs/WORKFLOW.md`, and the numbered files under
`docs/tasks/FILE-MGMT-001/`.

Validation: `git diff --check`; `git diff --cached --name-only`;
`git diff --cached --check`; focused `rg` for the new model terms.

Stop: register only if missing; stop if execution needs source/runtime changes
or historical task migration before the model exists.

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
