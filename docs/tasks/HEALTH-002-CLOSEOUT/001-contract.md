# HEALTH-002-CLOSEOUT - Contract

## Task

- ID: `HEALTH-002-CLOSEOUT`
- Type: docs-only status closeout
- Status target: `DONE`

## Objective

Reconcile the completed `HEALTH-002` frontend diagnostics panel task status
using committed evidence only.

## Allowed Files

- `docs/TASKS.md`
- `docs/tasks/HEALTH-002.md`
- `docs/tasks/HEALTH-002-CLOSEOUT/`

## Forbidden Files

- Source files
- Test files
- Frontend files
- Backend, database, worker, rollup, chat, audio, desktop, or Quick Capture
  behavior
- Runtime validation reruns that would broaden this docs-only task

## Evidence

- Implementation commit: `67e3bba feat: make core diagnostics visible before
  feature expansion`.
- `docs/PROJECT_STATE.md` records the Health / Diagnostics frontend panel as
  added.
- `docs/PROJECT_STATE.md` records HEALTH-002 validation facts including
  `scripts/validate.sh`, focused frontend tests, and compileall.

## Acceptance

- `HEALTH-002` is marked `DONE` in `docs/TASKS.md`.
- `docs/tasks/HEALTH-002.md` marks `HEALTH-002` as `DONE`.
- `HEALTH-002-CLOSEOUT` is marked `DONE` in `docs/TASKS.md`.
- The `HEALTH-002` capsule link is preserved.
- No source, test, frontend, backend, database, runtime, Quick Capture, or
  desktop files are changed.

## Stop Conditions

- Stop if committed evidence does not prove `HEALTH-002` was implemented.
- Stop if status reconciliation requires runtime inspection or source changes.
- Stop if files outside the allowed list would need changes.
