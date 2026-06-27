# Project State

This file records current project facts only. It is not a wishlist.

## Current Phase

Stabilization and observability before new feature expansion.

## Current Stable Baseline

- `79d7f8a Keep diary core importable while isolating unsafe surfaces`

## Latest Known Validation

- `scripts/validate.sh` -> pytest 48 passed in 1.54s and compileall passed during REPO-013
- `.venv/bin/python -m pytest -q` -> 48 passed in 1.53s during REPO-013
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` -> 48 passed in 1.53s during REPO-013
- `.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py` -> passed during REPO-013
- `.venv/bin/python -m pytest -q` -> 45 passed in 1.51s during REPO-011
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` -> 45 passed in 1.34s during REPO-010
- `rg -n "@app\.on_event|\.on_event\(" server.py api tests` absence check -> passed during BUG-002
- `.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py` -> passed without stale `desktop_app.py` noise during REPO-011

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
- Core Health / Diagnostics API added.
- FastAPI lifespan startup replaces deprecated `on_event` usage.
- Pytest cache provider disabled in project config for stable validation.
- Stale optional `desktop_app.py` target removed from canonical compileall validation.
- Repo-local validation wrapper added.

## Known Risks

- `.venv1` is obsolete/broken.
- `.venv` is the recommended development environment and currently validates the project.
- The configured global pre-push hook runs plain `pytest -q`; without the documented project environment override it resolves outside `.venv` and fails before a push.
- Hook-safe validation requires `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q` or `scripts/validate.sh`.
- Project pytest no longer requires an ad-hoc `PYTEST_ADDOPTS="-p no:cacheprovider"` override because `pytest.ini` disables the cache provider.
- System Python may not have the project test dependencies installed.
- Optional native audio dependencies can make the first pytest run look slow during cold start.
- Health / Diagnostics frontend panel not implemented.
- Quick Capture desktop companion not implemented.
- Image attachment ingest not implemented.

## Optional / Non-Core Modules

- Audio diary
- Voice chat
- Desktop packaging
- Quick Capture desktop companion
- Future plugin-like entry points

Optional modules must not become required dependencies of the core text diary system.
