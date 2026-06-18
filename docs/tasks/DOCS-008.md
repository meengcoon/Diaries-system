# DOCS-008 - Low-Token Governance Capsule

## Task

- ID: `DOCS-008`
- Mode: docs-only governance layout
- Status: DONE

## Read Policy

- Use the four-file control system.
- Do not dump full markdown files over 200 lines by default.
- Use `rg`, `sed` line ranges, `head`, or `tail` for indexed reads.
- Before a full read of a large markdown file, state why it is necessary.
- Prefer this task capsule or an ignored `CURRENT_TASK.md` capsule for active
  task context.

## Objective

Optimize the current four-file governance system so future Codex runs read less
markdown context while preserving task discipline, scope control, validation
gates, and stop conditions.

## Allowed Files

- `AGENTS.md`
- `docs/TASKS.md`
- `docs/WORKFLOW.md`
- `docs/PROJECT_STATE.md` only if facts need updating
- `CURRENT_TASK.md` only as an ignored local task capsule
- `.gitignore` only to ignore `CURRENT_TASK.md`
- `docs/tasks/<TASK_ID>.md` files if task capsules are introduced

## Forbidden Files

- Application source files
- Test files
- Product behavior changes
- Quick Capture, `HEALTH-002`, or implementation work
- Unrelated dirty or untracked files

## Relevant Facts

- The four-file governance intent is preserved:
  - `AGENTS.md` is permanent routing and hard rules.
  - `docs/PROJECT_STATE.md` is current facts only.
  - `docs/TASKS.md` is the task queue/index.
  - `docs/WORKFLOW.md` is the operating process and stop gates.
- `CURRENT_TASK.md` is a local ignored active-task capsule.
- Detailed task contracts may live under `docs/tasks/<TASK_ID>.md` when the task
  row would otherwise make `docs/TASKS.md` too large.
- Do not create a work-log system unless a future task explicitly needs one.

## Acceptance

- Codex has a clear rule to avoid full reads of large markdown files.
- The active task can be represented as a compact `CURRENT_TASK.md` capsule.
- `docs/TASKS.md` points to per-task capsule files where appropriate.
- Future Codex prompts can be short launchers that rely on `CURRENT_TASK.md` and
  indexed reads.
- No application code or tests are changed.

## Validation

```bash
git diff --check
git diff --cached --name-only
rg -n "DOCS-008|low-token|CURRENT_TASK|large markdown|task capsule" docs/TASKS.md AGENTS.md docs/WORKFLOW.md docs/PROJECT_STATE.md
```

Workflow pre-commit checks:

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
```

## Final Response Format

Start with one workflow label:

- `PASS_AND_COMMITTED`
- `TASK_REGISTERED_ONLY`
- `BLOCKED`
- `STOPPED`

Include selected task, files modified, files staged, commit hash if committed,
validation commands run, final git status, and confirmation that unrelated dirty
or untracked files were not touched.
