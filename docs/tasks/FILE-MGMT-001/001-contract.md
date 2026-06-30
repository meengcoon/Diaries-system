# FILE-MGMT-001 - Contract

## Task

- ID: `FILE-MGMT-001`
- Type: docs-only governance
- Status target: `DONE`

## Objective

Define the task-directory file management model so `docs/TASKS.md` remains a
task index and task details live in numbered files under
`docs/tasks/<TASK_ID>/`.

## Allowed Files

- `AGENTS.md`
- `docs/TASKS.md`
- `docs/WORKFLOW.md`
- `docs/tasks/FILE-MGMT-001/`

## Forbidden Files

- Application source files
- Test files
- Database, API, frontend, worker, rollup, chat, audio, desktop, or Quick
  Capture behavior
- Historical task migration
- Lossy compression of completed task history
- New work-log system
- Unrelated dirty or untracked files

## Required Model

- `docs/TASKS.md` is the task index.
- New detailed task content lives in `docs/tasks/<TASK_ID>/` directories.
- Task directory files use numeric prefixes such as `001-contract.md`.
- Existing `docs/tasks/<TASK_ID>.md` files remain legacy-compatible and are not
  migrated in this task.
- `CURRENT_TASK.md` remains ignored local scratch state.
- `.omx/` remains ignored runtime/planning state and must not be the only home
  for durable project rules.

## Acceptance

- `AGENTS.md` references task directories as the preferred active-task context.
- `docs/WORKFLOW.md` defines the index-vs-directory contract.
- `docs/WORKFLOW.md` defines numbered task document categories for contract,
  docs-governance, code-feature, optimization, validation, and archive/history
  content.
- `docs/WORKFLOW.md` defines 500 lines as the soft split trigger and 1000 lines
  as the hard limit for one task document.
- `docs/TASKS.md` records `FILE-MGMT-001` as complete and remains an index
  entry, not a long-form design spec.
- `docs/tasks/FILE-MGMT-001/` contains the detailed design, migration checklist,
  and validation notes.
- No historical task content is moved, deleted, summarized, or compressed.

## Stop Conditions

- Stop if implementing the model requires source, test, database, frontend, or
  runtime changes.
- Stop if historical migration becomes necessary before the model can be
  defined.
- Stop if lossy compression of old task content is requested without a separate
  approved migration task.
- Stop if validation requires files outside the allowed list.
