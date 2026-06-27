# HEALTH-002 - Core Health / Diagnostics Frontend Panel

## Task

- ID: `HEALTH-002`
- Status: READY
- Type: frontend-only UI/API integration

## Dependency Notes

- Depends on `HEALTH-001`.
- `HEALTH-001` is satisfied by `c80908a feat: expose core diagnostics without
  loading optional audio`.
- The diagnostics endpoint is `GET /api/health`.
- `GET /health` is the simple meta health endpoint and is not the diagnostics
  panel data source.
- Do not add, rename, or modify backend health routes in this task.

## Objective

Add a small frontend diagnostics panel/page that displays the existing backend
health summary for local operational visibility.

## Allowed Files

- `frontend/index.html`
- `frontend/app.js`
- `frontend/style.css`
- `tests/test_frontend_health_panel.py` only if needed for static frontend
  safety or rendering regression coverage
- `docs/PROJECT_STATE.md` only after successful implementation if recording the
  completed frontend panel as a current project fact

## Scope

- Add a small frontend diagnostics panel/page.
- Fetch health data from `GET /api/health`.
- Display only data already returned by the health endpoint; do not add backend
  fields in this task.
- Show DB path.
- Show job counts.
- Show FTS status.
- Show latest rollup state.
- Add loading and error states for health fetch failures.
- Keep the panel independent of audio, desktop, Quick Capture, and future
  plugin-like entry layers.
- Do not write directly to SQLite.
- Do not run model work from the frontend.
- Do not change API URLs, request/response payloads, database schema, upload
  behavior, audio behavior, desktop behavior, or Quick Capture behavior.

## Acceptance

- The frontend displays the health diagnostics data from `GET /api/health`.
- The panel shows DB path, job counts, FTS status, and latest rollup state.
- The panel handles loading and fetch-error states.
- The implementation does not introduce or depend on `GET /health` for
  diagnostics data.
- The implementation does not import or require optional audio-heavy modules.
- The implementation does not touch Quick Capture, `QC-*`, desktop, upload,
  worker, rollup, chat, or model-provider behavior.
- The implementation does not render untrusted health content as raw HTML.
- The implementation does not add new `innerHTML`, `dangerouslySetInnerHTML`, or
  raw markdown HTML rendering for health content.
- Existing backend validation still passes.

## Validation

```bash
git diff --check
git diff --cached --name-only
git diff --cached --check
rg -n "/api/health|health" frontend/index.html frontend/app.js frontend/style.css
if git diff -- frontend/index.html frontend/app.js frontend/style.css | rg -n "^\\+.*(innerHTML|dangerouslySetInnerHTML|marked\\.parse)"; then exit 1; fi
.venv/bin/python -m pytest -q tests/test_frontend_security.py
if [ -f tests/test_frontend_health_panel.py ]; then .venv/bin/python -m pytest -q tests/test_frontend_health_panel.py; fi
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py
```

## Stop Conditions

- Stop if the health panel requires backend route changes or new health response
  fields.
- Stop if implementation cannot consume `GET /api/health` without changing API
  URLs.
- Stop if the work requires using `GET /health` as the diagnostics data source.
- Stop if validation requires new dependencies or frontend build/test
  infrastructure that is not already present.
- Stop if source inspection shows the exact allowed file list is insufficient.
- Stop if the work would broaden into Quick Capture, any `QC-*` task, desktop,
  upload/file behavior, audio/STT, worker, rollup, chat, or model-provider work.
