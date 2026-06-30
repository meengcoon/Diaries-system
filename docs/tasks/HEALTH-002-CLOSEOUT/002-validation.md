# HEALTH-002-CLOSEOUT - Validation

## Validation Goal

Prove that `HEALTH-002` status is reconciled using committed evidence only and
that no implementation files were touched.

## Required Commands

```bash
git status --short --branch
git show --name-only --format=fuller --no-renames 67e3bba
git diff --check
sed -n '2120,2210p' docs/TASKS.md
sed -n '1,24p' docs/tasks/HEALTH-002.md
rg -n "HEALTH-002-CLOSEOUT|67e3bba|docs/tasks/HEALTH-002-CLOSEOUT|docs/tasks/HEALTH-002.md" docs/TASKS.md docs/tasks/HEALTH-002-CLOSEOUT
rg -n "Health / Diagnostics frontend panel added|pytest 48 passed and compileall passed during HEALTH-002" docs/PROJECT_STATE.md
find docs/tasks/HEALTH-002-CLOSEOUT -maxdepth 1 -type f -print0 | xargs -0 wc -l
git diff --cached --name-only
git diff --cached --check
```

## Expected Scope

Changed files must be limited to:

- `docs/TASKS.md`
- `docs/tasks/HEALTH-002.md`
- `docs/tasks/HEALTH-002-CLOSEOUT/001-contract.md`
- `docs/tasks/HEALTH-002-CLOSEOUT/002-validation.md`

## Runtime Test Policy

Do not rerun pytest or compileall in this task. `HEALTH-002-CLOSEOUT` is a
docs-only status reconciliation task and relies on the already committed
validation evidence from `67e3bba` and `docs/PROJECT_STATE.md`.
