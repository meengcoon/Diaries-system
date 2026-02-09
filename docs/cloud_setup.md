# Cloud Setup (Diary System)

## 1) Enable multi-provider routing for chat

Set env vars before starting server:

```bash
export CLOUD_ENABLED=1
export CLOUD_DEFAULT_PROVIDER=deepseek   # or qwen
export DEEPSEEK_API_KEY="<your_deepseek_key>"
export DASHSCOPE_API_KEY="<your_qwen_key>"
# Optional
export DEEPSEEK_MODEL="deepseek-chat"
export QWEN_CLOUD_MODEL="qwen-plus"
```

Routing file: `bot/generation_router.py`

Main routing inputs:
- `force_local=true` => always local
- `force_cloud=true` => always cloud (if key/provider is valid)
- `preferred_provider=deepseek|qwen`
- privacy/size/feature gates in env (e.g. `CLOUD_CHAR_THRESHOLD`, `CLOUD_MAX_PRIVACY_LEVEL`)

`/api/chat` now supports these fields:
- `preferred_provider`
- `force_cloud`
- `force_local`

## 2) Enable upload/sync of diary text to cloud

This is a separate pipeline from chat routing.

```bash
export CLOUD_SYNC_ENABLED=1
export CLOUD_SYNC_URL="https://your-cloud-endpoint.example.com/analyze"
export CLOUD_SYNC_API_KEY="<optional_bearer_token>"
export CLOUD_SYNC_TIMEOUT_S=20
```

Behavior:
- On `POST /api/diary/save`, system builds privacy contract locally and queues background sync.
- If cloud returns a `result_contract` (or equivalent payload with `blocks`), it is applied into local DB.
- Sync is incremental per diary file (`cloud_sync_state` stores synced byte watermark).
- Watermark advances only after cloud result is successfully applied locally.

Manual sync existing files:

```bash
curl -X POST http://127.0.0.1:8000/api/diary/cloud/sync_existing \
  -H 'Content-Type: application/json' \
  -d '{"limit": 30, "newest_first": true}'

curl http://127.0.0.1:8000/api/diary/cloud/state
```

## 3) Check active bot and routes

```bash
curl http://127.0.0.1:8000/api/_bot
curl http://127.0.0.1:8000/api/_routes
```

You should see `CascadeBot` in `/api/_bot` if routing is active.
