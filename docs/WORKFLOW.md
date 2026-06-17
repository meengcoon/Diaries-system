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
  Single source of truth for actionable tasks.
- `docs/WORKFLOW.md`
  Step-by-step operating process.

## Non-negotiable rule

Do not execute or invent tasks that are not listed in `docs/TASKS.md`.

If a needed task is missing, update `docs/TASKS.md` first in a docs-only task.

## Task Start Gate

A task can begin only if:

- The task exists in `docs/TASKS.md`.
- The selected task ID is explicit.
- The task has a goal, allowed files, acceptance criteria, and validation.
- Dependencies are satisfied, or the user explicitly chooses to work on a blocked task for diagnosis only.

If any of these are missing, stop and update `docs/TASKS.md` first in a docs-only task.

## Task Completion Gate

A task is complete only when:

- All acceptance criteria for the selected task are satisfied, or a blocker is clearly reported.
- All required validation commands have passed, or skipped checks are explicitly justified.
- Changed files are limited to the allowed files.
- No unrelated dirty files were touched.
- Nothing is staged unless the task explicitly requires staging or committing.
- If the task requires a commit, the commit contains only the allowed files and the commit hash is reported.
- The final report includes changed files, checks run, results, risks, and blockers.

Once these conditions are met, stop.

## Stop Conditions

Codex must stop immediately and report if:

- The task is missing from `docs/TASKS.md`.
- The task lacks allowed files, acceptance criteria, or validation.
- A required change would touch files outside the allowed list.
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

1. Identify the task ID in `docs/TASKS.md`.
2. Confirm its status is READY, TODO, or explicitly selected by the user.
3. Read:
   - `AGENTS.md`
   - `docs/PROJECT_STATE.md`
   - `docs/TASKS.md`
   - this workflow document
4. Confirm allowed files.
5. Run `git status --short`.
6. Avoid unrelated dirty files.
7. Modify only files allowed by the task.
8. Add or update tests for bugfixes and behavior changes.
9. Run validation commands listed in the task.
10. Report changed files, checks, risks, and skipped checks.
11. Stage only explicit files.
12. Commit with a focused message.
13. Update `docs/PROJECT_STATE.md` only when project facts changed.
14. Update `docs/TASKS.md` task status after completion.

## Prompt discipline

Future prompts should be short launchers, not full ad-hoc task definitions.

They should say:

```text
Work on TASK <TASK-ID> only.
Read AGENTS.md, docs/PROJECT_STATE.md, docs/TASKS.md, and docs/WORKFLOW.md.
Use docs/TASKS.md as the source of truth.
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
git diff --cached --name-only
git diff --cached --check
```

## Validation defaults

For normal backend/frontend changes:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
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
