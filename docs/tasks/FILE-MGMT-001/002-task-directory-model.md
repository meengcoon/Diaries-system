# FILE-MGMT-001 - Task Directory Model

## Purpose

The task system has two layers:

- `docs/TASKS.md` is the task index and status authority.
- `docs/tasks/<TASK_ID>/` is the durable home for detailed task material.

This prevents the task index from growing into a long-form archive while still
keeping enough information in the index for future agents to find the correct
task and stop at the right boundary.

## Authority Map

`AGENTS.md`:

- Permanent agent rules and hard constraints.
- Highest-level workflow instructions that future agents must read.

`docs/PROJECT_STATE.md`:

- Current project facts only.
- Not a task log, backlog, or design archive.

`docs/TASKS.md`:

- Task existence and task status authority.
- Stores task ID, status, dependencies, short goal, task directory path, and key
  document paths.
- Should not store long contracts, detailed validation logs, implementation
  evidence, or historical narratives once a task directory exists.

`docs/tasks/<TASK_ID>/`:

- Detailed task contract and supporting documents.
- Stores allowed files, forbidden files, acceptance criteria, validation,
  design notes, migration checklists, and completion evidence for that task.

`CURRENT_TASK.md`:

- Ignored local scratch for the active run.
- May summarize the selected task for convenience.
- Must not become committed authority.

`.omx/`:

- Ignored runtime, interview, planning, and agent state.
- Useful as source context, but not the only durable home for long-lived rules.

## Directory Shape

New detailed tasks should use:

```text
docs/tasks/<TASK_ID>/
  001-contract.md
  002-<topic>.md
  003-<topic>.md
```

The first file should be `001-contract.md` unless the task has a stronger
existing convention. It should contain the task objective, allowed files,
forbidden files, acceptance criteria, validation, and stop conditions.

## Numbered Document Categories

Use category-specific numbered files when content would otherwise bloat the
task index:

- `001-contract.md` for the executable task contract.
- `002-docs-governance.md` or similar for documentation rules and file
  placement decisions.
- `00N-code-feature.md` for feature implementation notes, when a code task
  needs detailed design before execution.
- `00N-optimization.md` for cleanup, compaction, performance, or quality
  optimization notes.
- `00N-validation.md` for validation commands, evidence, and completion checks.
- `00N-archive.md` or `00N-history.md` for archive/history decisions.

The exact topic slug can vary, but the numeric prefix must preserve reading
order.

## Split Rules

- 500 lines is the soft split trigger.
- 1000 lines is the hard limit for one task document.
- When a document crosses 500 lines, future additions should usually go into the
  next numbered file.
- A document must not exceed 1000 lines unless a future task explicitly records
  why splitting would damage the record.
- New numbered files must be linked from the task index or from
  `001-contract.md` so future agents can find them.

## Legacy Compatibility

Existing single-file capsules such as `docs/tasks/HEALTH-002.md` remain valid.
They are legacy-compatible task capsules and are not migrated by this task.

New tasks should prefer task directories. Existing single-file capsules should
be moved or split only by a separate migration task with explicit approval.

## Archive And History

Archive/history content must be lossless unless a separate approved task allows
summarization. A future migration task may define an archive location such as
`docs/tasks/archive/`, but this task only defines the governance model and does
not move historical records.
