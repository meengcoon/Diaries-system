# Workflow Runbook

## Purpose

This document is the canonical operating workflow for future Codex runs and manual development steps.

It prevents prompt drift, accidental task invention, broad edits, unsafe staging, and inconsistent validation.

## Control documents

- `AGENTS.md`
  Hard rules for Codex and future AI agents.
- `docs/PROJECT_STATE.md`
  Current facts only. Not a wishlist.
- `docs/TASKS.md`
  Single source of truth for task status and task-capsule links.
- `docs/WORKFLOW.md`
  Step-by-step operating process.

## Low-Token Read Policy

- Do not dump full markdown files over 200 lines by default.
- Use `rg`, `sed` line ranges, `head`, or `tail` to read the relevant section.
- Before reading a large markdown file in full, state why the full read is
  necessary for the selected task.
- Prefer the active `CURRENT_TASK.md` capsule and per-task files under
  `docs/tasks/<TASK_ID>.md` over historical task text in `docs/TASKS.md`.
- Keep `docs/TASKS.md` as an index: status, dependencies, short goal, and a link
  to a task capsule when the full contract is long.
- Keep `docs/PROJECT_STATE.md` factual and current; do not use it as a task log.
- Keep `docs/WORKFLOW.md` focused on operating process and stop gates.
- Do not create a work-log system unless a future task explicitly requires it.

## Current Task Capsule

`CURRENT_TASK.md` is an ignored local handoff file for the active task. It may be
created by a prompt or by the agent before implementation, then left uncommitted.

A compact capsule should include:

- task ID
- mode
- read policy
- objective
- allowed files
- forbidden files
- relevant facts
- validation commands
- acceptance criteria
- final response format

## Non-negotiable rule

Work on exactly one task per run. Do not execute or invent tasks that are not listed in `docs/TASKS.md`.

If the intended task is missing, update `docs/TASKS.md` in a docs-only registration pass, then stop with `TASK_REGISTERED_ONLY`.
Do not combine registration and implementation unless the task explicitly allows it.

## Task Start Gate

A task can begin only if:

- The task exists in `docs/TASKS.md`.
- The selected task ID is explicit.
- The task row or matching task capsule has a goal, allowed files, acceptance
  criteria, and validation.
- If a task capsule exists, it matches the selected task ID and does not widen
  the allowed files in `docs/TASKS.md`.
- Dependencies are satisfied, or the user explicitly chooses to work on a blocked task for diagnosis only.
- `git status --short` has been inspected and unrelated dirty or untracked files are treated as protected existing state.

If any of these are missing, stop and update `docs/TASKS.md` first in a docs-only task.

## Task Completion Gate

A task is complete only when:

- All acceptance criteria for the selected task are satisfied, or a blocker is clearly reported.
- All required validation commands have passed, or skipped checks are explicitly justified.
- Changed files are limited to the allowed files.
- No unrelated dirty or untracked files were touched, staged, or committed.
- Nothing is staged unless the task explicitly requires staging or committing.
- If the task requires a commit, the cached diff contains only the allowed files, the commit maps to one task, and the commit hash is reported.
- The final response uses one of the required labels and includes the required evidence fields.

Once these conditions are met, stop.

## Stop Conditions

Codex must stop immediately and report if:

- The task is missing from `docs/TASKS.md`.
- The task lacks allowed files, acceptance criteria, or validation.
- A required change would touch files outside the allowed list.
- Completion or validation requires touching files outside the selected task scope.
- Validation fails.
- A dependency is unmet.
- There are unexpected staged files.
- The requested work would broaden into a different task.
- A new issue is discovered that is not required to satisfy the current task.

## Anti-Loop Rule

- Do not continue polishing docs, rules, prompts, or architecture once the selected task's acceptance criteria are met.
- Do not create additional docs-only tasks unless the current task cannot safely proceed without them.
- For new issues discovered during a task, add or propose a separate task in `docs/TASKS.md` instead of fixing it opportunistically.
- For implementation tasks, do not perform "while here" cleanup.
- For docs tasks, stop when the requested rule or section exists and validation passes.

## Standard operating loop

1. Identify the task ID in `docs/TASKS.md` using indexed reads.
2. Confirm its status is READY, TODO, or explicitly selected by the user.
3. Read:
   - `AGENTS.md`
   - `docs/PROJECT_STATE.md`
   - the selected task row in `docs/TASKS.md`
   - `CURRENT_TASK.md` or `docs/tasks/<TASK_ID>.md` if present
   - this workflow document
4. Confirm allowed files.
5. Run `git status --short`.
6. Treat unrelated dirty or untracked files as protected existing state.
7. Modify only files allowed by the task.
8. Add or update tests for bugfixes and behavior changes.
9. Run focused validation for the changed behavior before broader validation when both apply.
10. If validation requires out-of-scope changes, stop as `BLOCKED` and record the blocker instead of widening scope.
11. Run validation commands listed in the task.
12. Stage only explicit allowed files or hunks.
13. Run the required pre-commit diff checks.
14. Commit with a focused message only when the cached diff is task-scoped.
15. Update `docs/PROJECT_STATE.md` only when project facts changed.
16. Update `docs/TASKS.md` task status only when allowed by the task.

## Prompt discipline

Future prompts should be short launchers, not full ad-hoc task definitions.

They should say:

```text
Work on TASK <TASK-ID> only.
Read AGENTS.md, docs/PROJECT_STATE.md, docs/TASKS.md, and docs/WORKFLOW.md.
Use docs/TASKS.md as the source of truth and read any matching task capsule.
Do not modify files outside the task allowed list.
Do not stage or commit unless explicitly told.
```

## Git discipline

Never use:

```bash
git add .
git add docs/
git add tests/
```

Use explicit staging only:

```bash
git add <file1> <file2>
```

Before committing, always run:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
```

`git diff --cached --name-only` must show only files allowed by the selected task.

## Final response labels

Start the final response with exactly one of:

- `PASS_AND_COMMITTED`
- `TASK_REGISTERED_ONLY`
- `BLOCKED`
- `STOPPED`

Final responses must include:

- selected task
- files modified
- files staged
- commit hash if committed
- validation commands run
- final git status
- confirmation that unrelated dirty or untracked files were not touched

## Validation defaults

For normal backend/frontend changes:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py
```

For import-boundary changes:

Verify importing `api.routes_diary` and `server` does not load audio-heavy modules.

For frontend security changes:

Run or update frontend security tests.

For upload/file changes:

Test size limits, MIME validation, and rejected files not being persisted.

## Current planned sequence

1. TEST-001 - Commit core E2E and extreme input regression tests.
2. DOCS-002 - Commit project control documents.
3. REPO-001 - Audit dirty worktree.
4. BUG-001 - Rebuild or replace broken local virtualenv.
5. BUG-002 - Replace deprecated FastAPI on_event usage.
6. HEALTH-001 - Core Health / Diagnostics API.
7. HEALTH-002 - Core Health / Diagnostics frontend panel.
8. QC-001 - Quick Capture backend contract.
9. QC-002 - Quick Capture text-only backend endpoint.
10. QC-002B - Verify Quick Capture participates in core chain.
11. ATTACH-001 - Design image attachment storage.
12. ATTACH-002 - Add image attachment persistence.
13. ATTACH-003 - Add safe image attachment ingest.
14. QC-003 - Add image support to quick capture endpoint.
15. DESKTOP-001 - Confirm Quick Capture desktop approach.
16. DESKTOP-002 - Add text-only Quick Capture desktop shell.
17. DESKTOP-003 - Add image input to Quick Capture desktop shell.

## When to update PROJECT_STATE

Update `docs/PROJECT_STATE.md` only when a stable project fact changes, such as:

- a feature is completed and validated
- a risk is removed
- a new known risk is discovered
- the stable baseline changes
- validation status changes
- optional modules become implemented or explicitly deferred

Do not put wishlist items in `PROJECT_STATE.md`.

## When to update TASKS

Update `docs/TASKS.md` when:

- adding a new task
- changing task status
- adding acceptance criteria
- adding dependencies
- marking a task DONE / BLOCKED / WONTFIX
- splitting a task that is too large
- adding or updating a link to `docs/tasks/<TASK_ID>.md`

Do not implement a task in the same run if the only requested work was to register that task.

## When to create a plan file

Create `docs/PLANS/<task-id>.md` only for large tasks involving:

- database schema changes
- new entry layers
- file/image storage
- desktop app behavior
- security/privacy boundary changes
- multi-commit work

## Current product direction

The product remains a local-first diary and personal memory system.

Core chain:

```text
save -> blocks -> jobs -> worker -> rollup -> FTS -> context_pack/chat
```

Optional layers such as audio, desktop, Quick Capture, and future plugin-like entry points must not become required dependencies of the core text diary system.
