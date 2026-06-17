# Project State

This file records current project facts only. It is not a wishlist.

## Current Phase

Stabilization and observability before new feature expansion.

## Current Stable Baseline

- `79d7f8a Keep diary core importable while isolating unsafe surfaces`

## Latest Known Validation

- `python3 -m pytest -q` -> 36 passed
- `python3 -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py desktop_app.py` -> passed
- `.venv/bin/python -m pip --version` -> pip 24.0
- `.venv/bin/python -m pytest -q` -> 36 passed, 2 warnings

## Core Product Direction

Local-first diary and personal memory system.

## Core Chain

```text
save -> blocks -> jobs -> worker -> rollup -> FTS -> context_pack/chat
```

## Core Invariants

- Text diary CRUD must not depend on audio, STT, numpy, or ffmpeg.
- Save path must not run model work synchronously.
- Worker results must respect entry version.
- Rollup must feed `entry_analysis` and FTS.
- Chat context must be grounded in saved entries, blocks, or memory.
- Frontend must not render untrusted model or user content as raw HTML.
- Upload endpoints must have size limits.

## Done

- Core import boundary fixed.
- Audio route isolated.
- Voice upload size cap added.
- Frontend raw markdown HTML removed.
- Full pytest passes.
- Fake-provider E2E added.
- Extreme input tests added.

## Known Risks

- `.venv1` is obsolete/broken.
- `.venv` is the recommended development environment and currently validates the project.
- System Python may not have `pytest` installed.
- FastAPI `on_event` deprecation warning remains.
- Health / Diagnostics page not implemented.
- Quick Capture desktop companion not implemented.
- Image attachment ingest not implemented.

## Optional / Non-Core Modules

- Audio diary
- Voice chat
- Desktop packaging
- Quick Capture desktop companion
- Future plugin-like entry points

Optional modules must not become required dependencies of the core text diary system.
