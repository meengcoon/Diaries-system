# FILE-MGMT-001 - Migration Checklist

## Purpose

This checklist defines how a future migration task should classify existing
task content. It is not approval to move, delete, summarize, or compress any
historical task record.

## Migration Gate

A future migration task must:

- Exist in `docs/TASKS.md` before execution.
- List allowed files explicitly.
- Preserve historical task records losslessly unless the user explicitly
  approves summarization.
- Keep active and blocked task status discoverable in `docs/TASKS.md`.
- Stop if a record contains ambiguous product, blocker, dependency, validation,
  or commit evidence.

## Classification Buckets

Use these buckets for each existing task record:

- Keep in index: short active, blocked, parked, or next-action task rows.
- Create task directory: active or future executable tasks that need more than a
  short index row.
- Keep legacy capsule: existing `docs/tasks/<TASK_ID>.md` files that remain
  readable and below split thresholds.
- Archive losslessly: completed task records whose details should be preserved
  exactly in a tracked archive.
- Summarize only with confirmation: older completed records where a concise
  summary is useful but lossy compression requires user approval.
- Leave untouched: ambiguous records or records tied to unresolved blockers.

## Future Migration Template

```markdown
| Task ID | Current home | Status | Recommended action | Reason | User review |
| --- | --- | --- | --- | --- | --- |
| TASK-ID | docs/TASKS.md | DONE | Archive losslessly | Keeps validation evidence | No |
```

## Non-Migration Commitment

`FILE-MGMT-001` defines the model only. It does not:

- Move old task rows.
- Split existing legacy capsules.
- Create `docs/tasks/archive/`.
- Rewrite `docs/TASKS.md` history.
- Compress completed task evidence.
- Register a broad work-log system.

## Recommended Follow-Up Shape

If migration is needed later, register a separate task such as:

```text
FILE-MGMT-002 - Classify existing task history for directory migration
```

That task should produce a reviewed migration table before any archival move.
