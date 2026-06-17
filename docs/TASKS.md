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

## DOCS-008 - Optimize Governance Docs for Low-Token Task Capsules

Status: BLOCKED

Depends on:

- `REPO-002`

Goal:

Optimize the current four-file governance system so future Codex runs read less markdown context while preserving task discipline, scope control, validation gates, and stop conditions.

Problem:

The current four-file system controls Codex behavior, but it can still waste tokens if Codex repeatedly reads full markdown files such as `AGENTS.md`, `docs/TASKS.md`, `docs/WORKFLOW.md`, or future logs. The next optimization is not to add more governance documents, but to make the existing system route Codex toward small task capsules and indexed reads.

Do not implement until:

- `REPO-002` has inspected the remaining dirty worktree diffs.
- The team has decided what to do with existing dirty source/test files.
- The repo is safe enough for a docs-structure change.

Target design:

- Keep `AGENTS.md` short and permanent.
- Add a large markdown read policy:
  - Do not cat full markdown files over 200 lines.
  - Use `rg`, `grep`, `sed` line ranges, `head`, or `tail`.
  - Prefer indexes and task capsules over full historical files.
  - Before reading a large markdown file, state why it is necessary.
- Add or define `CURRENT_TASK.md` as the current task capsule.
- Make `CURRENT_TASK.md` self-contained for the active task:
  - task ID
  - mode
  - read policy
  - objective
  - allowed files
  - forbidden files
  - relevant facts
  - commands
  - acceptance
  - final response format
- Keep `docs/TASKS.md` as a task index instead of a growing full task-contract file.
- Move detailed task contracts into `docs/tasks/<TASK_ID>.md` where appropriate.
- Keep `docs/PROJECT_STATE.md` as current facts only.
- Keep `docs/WORKFLOW.md` focused on operating process and stop gates, not task history.
- Do not create a WORK_LOG system unless the diary project actually needs historical logs later.

Allowed files for the future DOCS-008 execution:

- `AGENTS.md`
- `docs/TASKS.md`
- `docs/WORKFLOW.md`
- `docs/PROJECT_STATE.md` only if facts need updating
- `CURRENT_TASK.md` if introduced as an ignored task capsule
- `.gitignore` only if `CURRENT_TASK.md` must be ignored
- `docs/tasks/<TASK_ID>.md` files if task capsules are introduced

Scope:

- Design and implement the low-token governance layout.
- Do not modify application code.
- Do not modify tests.
- Do not change product behavior.
- Do not use this task to clean unrelated dirty files.

Acceptance:

- DOCS-008 preserves the four-file governance intent:
  - `AGENTS.md` = permanent routing and hard rules
  - `docs/PROJECT_STATE.md` = current facts only
  - `docs/TASKS.md` = task queue/index
  - `docs/WORKFLOW.md` = operating process and stop gates
- Codex has a clear rule to avoid full reads of large markdown files.
- The active task can be represented as a compact `CURRENT_TASK.md` capsule.
- `docs/TASKS.md` either remains manageable or points to per-task capsule files.
- No application code or tests are changed.
- Future Codex prompts can be short launchers that rely on `CURRENT_TASK.md` and indexed reads.

Validation:

```bash
git diff --check
git diff --cached --name-only
rg -n "DOCS-008|low-token|CURRENT_TASK|large markdown|task capsule" docs/TASKS.md AGENTS.md docs/WORKFLOW.md docs/PROJECT_STATE.md
```

## REPO-001 - Audit Dirty Worktree

Status: READY

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

Status: READY

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

Status: READY

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

Status: READY

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

Status: READY

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
