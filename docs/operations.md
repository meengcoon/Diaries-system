# Runtime Operations

## Development startup

Start the API:

```bash
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Start the analysis worker in a second terminal:

```bash
.venv/bin/python scripts/run_block_jobs.py \
  --backend cloud \
  --preferred-provider deepseek \
  --retry-failed \
  --force \
  --loop \
  --poll-seconds 5
```

For local-only analysis:

```bash
.venv/bin/python scripts/run_block_jobs.py \
  --backend local \
  --retry-failed \
  --force \
  --loop \
  --poll-seconds 5
```

## Queue and health checks

API health:

```bash
curl http://127.0.0.1:8000/health
```

Queue summary from API:

```bash
curl http://127.0.0.1:8000/api/diary/analyze_status
```

Queue summary from worker CLI:

```bash
.venv/bin/python scripts/run_block_jobs.py --stats
```

Normal queue progression:

- new save/update/reanalyze request creates `pending` jobs
- worker claims jobs and briefly moves them to `running`
- completed jobs become `done`
- entry rollup appears in `entry_analysis`

## Common failure symptoms

### API does not start

Check port occupancy:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

If needed, start on another port:

```bash
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8001
```

### Jobs remain `pending`

Usually means the worker is not running, or the worker started without `--force` and skipped due to idle gating.

Check:

```bash
.venv/bin/python scripts/run_block_jobs.py --stats
```

If `pending > 0` and `running = 0` for a long time, the worker is not consuming.

### Worker prints `reason = not_idle`

That is expected if the worker is started without `--force` and the machine is active.

Use the fixed development command with `--force`.

### Request succeeded but analysis never appears

Check both:

- `/api/diary/analyze_status`
- worker terminal output

If requests return `analysis_queued=true` but `pending` never decreases, the queue is healthy and the worker path is the problem.
