# FILE-MGMT-001 - Validation

## Focus

Validation proves that the task-directory governance model exists in tracked
docs, the task index remains compact, and no runtime files were touched.

## Required Commands

```bash
git diff --check
rg -n "task-directory|docs/tasks/<TASK_ID>|500 lines|1000 lines|CURRENT_TASK|\\.omx" AGENTS.md docs/WORKFLOW.md docs/tasks/FILE-MGMT-001
rg -n "FILE-MGMT-001|docs/tasks/FILE-MGMT-001|001-contract|002-task-directory-model|003-migration-checklist|004-validation|Status: DONE" docs/TASKS.md
find docs/tasks/FILE-MGMT-001 -maxdepth 1 -type f -print0 | xargs -0 wc -l
git diff --cached --name-only
git diff --cached --check
git status --short --branch
```

## Expected Scope

Changed files must be limited to:

- `AGENTS.md`
- `docs/TASKS.md`
- `docs/WORKFLOW.md`
- `docs/tasks/FILE-MGMT-001/001-contract.md`
- `docs/tasks/FILE-MGMT-001/002-task-directory-model.md`
- `docs/tasks/FILE-MGMT-001/003-migration-checklist.md`
- `docs/tasks/FILE-MGMT-001/004-validation.md`

## Expected Evidence

- `FILE-MGMT-001` is marked `DONE` in `docs/TASKS.md`.
- `docs/TASKS.md` points to the task directory and numbered documents.
- `AGENTS.md` and `docs/WORKFLOW.md` reference task directories, with legacy
  single-file capsules treated as compatible older records.
- The 500-line and 1000-line split rules are searchable.
- Each new task document is below 500 lines.
- No source, test, database, frontend, worker, audio, desktop, or Quick Capture
  files are changed.

## Commit Checks

Before committing:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
```

The cached file list must contain only the expected scope above.
