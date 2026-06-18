# Diary System Agent Instructions

This repository is a local-first diary and personal memory system.

The core pipeline is:

```text
save -> blocks -> jobs -> worker -> rollup -> FTS -> context_pack/chat
```

## Hard Rules

- Do not bypass the existing ingest pipeline.
- Inspect `git status --short` before starting any task.
- Execute exactly one task per run, and only if it is listed in `docs/TASKS.md`.
  If the intended task is missing, register it in `docs/TASKS.md` only, then stop.
  Do not combine task registration and implementation unless the task explicitly allows it.
- Codex must stop after the selected task's acceptance criteria and validation are satisfied.
  Stop immediately after a successful task commit.
  Do not continue polishing docs, broadening scope, or fixing adjacent or newly discovered issues unless required by the selected task. Record new issues as separate tasks in `docs/TASKS.md`.
- Treat unrelated dirty and untracked files as existing project/user state.
  Do not modify, format, delete, stage, or commit unrelated dirty or untracked files.
- New entry-like inputs must go through the backend API and the existing ingest, queue, and rollup path.
- Do not write directly to SQLite from the frontend, desktop app, Quick Capture app, or scripts unless the task explicitly authorizes it.
- The text diary core must remain usable without audio, STT, numpy, ffmpeg, faster-whisper, or desktop dependencies.
- `api.routes_diary` and `server` must not import:
  - `pipeline.audio_features`
  - `services.audio_ingest_service`
  - `numpy`
  - `faster_whisper`
  - ffmpeg-dependent code
- Do not reintroduce unsafe raw HTML rendering for model or user content.
- Do not use unsafe `innerHTML` with untrusted content.
- Upload and file endpoints must have explicit size limits and tests.
- Preserve existing API URLs unless a task explicitly authorizes breaking changes.
- Audio, desktop, Quick Capture, and future plugin-like entry layers must remain optional.
- Do not perform broad refactors unless the task is explicitly marked as refactor.
- Each commit must correspond to one task and contain only that task's allowed files or hunks.
- Never use `git add .` or broad staging commands.
  Stage only explicit files or explicit hunks allowed by the selected task.
- Before committing, confirm the staged diff contains only task-allowed files with `git diff --cached --name-only` and `git diff --cached --check`.

## Required Checks

For normal backend/frontend changes:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py
```

For import-boundary changes:

- Verify importing `api.routes_diary` and `server` does not load audio-heavy modules.

For frontend security changes:

- Run or update frontend security tests.

For upload/file changes:

- Add tests for size limits, MIME validation, and rejected files not being persisted.

## Task Workflow

Before editing:

- Read `docs/PROJECT_STATE.md`.
- Read `docs/TASKS.md`.
- Before executing implementation or bugfix tasks, read the canonical workflow runbook:
  `docs/WORKFLOW.md`.
- Identify the exact task ID.
- State intended files to touch.

During editing:

- Keep changes scoped to the task.
- Add regression tests for bugfixes.
- Avoid opportunistic cleanup.

After editing:

- Report changed files.
- Report tests/checks run.
- Report risks or skipped checks.

## Commit Discipline

- Use focused commits only.
- Use these commit prefixes:
  - `fix:`
  - `test:`
  - `docs:`
  - `feat:`
  - `refactor:`
  - `chore:`
