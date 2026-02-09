from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from pipeline.contract_apply import apply_result_contract
from pipeline.privacy_gate import build_cloud_contract_v1
from storage.db_core import _utc_now_iso, connect

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def cloud_sync_enabled() -> bool:
    return _env_bool("CLOUD_SYNC_ENABLED", False) and bool((os.getenv("CLOUD_SYNC_URL") or "").strip())


def _sanitize_header_token(raw: str) -> str:
    # Remove accidental wrapping quotes/spaces from shell copy-paste.
    t = str(raw or "").strip().strip("'").strip('"').strip()
    return t


def _validate_ascii_header_token(token: str) -> Optional[str]:
    if not token:
        return None
    try:
        token.encode("ascii")
    except UnicodeEncodeError:
        return "CLOUD_SYNC_API_KEY contains non-ASCII characters; use a real ASCII token or unset it."
    return None


def _post_json(url: str, payload: Dict[str, Any], *, api_key: str = "", timeout_s: float = 20.0) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _extract_result_contract(resp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if isinstance(resp.get("result_contract"), dict):
        return resp["result_contract"]
    if isinstance(resp.get("payload"), dict) and isinstance(resp["payload"].get("blocks"), list):
        return resp["payload"]
    if isinstance(resp.get("blocks"), list):
        return resp
    return None


def _get_sync_state(file_path: str) -> Dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT file_path, synced_bytes, last_file_size, last_status, last_error, updated_at "
            "FROM cloud_sync_state WHERE file_path=? LIMIT 1",
            (file_path,),
        ).fetchone()
        if not row:
            return {"file_path": file_path, "synced_bytes": 0, "last_file_size": 0, "last_status": "init"}
        return dict(row)
    finally:
        conn.close()


def _upsert_sync_state(
    *,
    file_path: str,
    synced_bytes: int,
    last_file_size: int,
    source: str,
    status: str,
    error: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO cloud_sync_state(
                file_path, synced_bytes, last_file_size, last_source,
                last_batch_id, last_status, last_error, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                synced_bytes=excluded.synced_bytes,
                last_file_size=excluded.last_file_size,
                last_source=excluded.last_source,
                last_batch_id=excluded.last_batch_id,
                last_status=excluded.last_status,
                last_error=excluded.last_error,
                updated_at=excluded.updated_at
            """,
            (
                file_path,
                int(max(0, synced_bytes)),
                int(max(0, last_file_size)),
                source,
                batch_id,
                status,
                (error or "")[:1000] if error else None,
                _utc_now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def sync_diary_text_to_cloud(raw_text: str, *, source: str = "api_diary_save") -> Dict[str, Any]:
    """Upload redacted text to cloud and apply returned contract locally.

    Success criteria for this function: cloud upload succeeded + local apply succeeded.
    """
    text = str(raw_text or "").strip()
    if not text:
        return {"ok": False, "error": "empty_text"}

    if not cloud_sync_enabled():
        return {"ok": False, "error": "cloud_sync_disabled"}

    cloud_url = (os.getenv("CLOUD_SYNC_URL") or "").strip()
    api_key = _sanitize_header_token(os.getenv("CLOUD_SYNC_API_KEY") or "")
    token_err = _validate_ascii_header_token(api_key)
    if token_err:
        logger.warning(f"cloud_sync config error: {token_err}")
        return {"ok": False, "uploaded": False, "error": token_err}
    timeout_s = float(os.getenv("CLOUD_SYNC_TIMEOUT_S", "20"))

    contract = build_cloud_contract_v1(raw_text=text, source=source)

    try:
        resp = _post_json(cloud_url, contract, api_key=api_key, timeout_s=timeout_s)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        msg = f"http_{e.code}: {body[:300]}"
        logger.warning(f"cloud_sync http error: {msg}")
        return {"ok": False, "uploaded": False, "error": msg}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        logger.warning(f"cloud_sync failed: {msg}")
        return {"ok": False, "uploaded": False, "error": msg}

    result_contract = _extract_result_contract(resp)
    if not result_contract:
        # Not complete yet: server acknowledged but no analyzable result contract returned.
        return {"ok": False, "uploaded": True, "applied": False, "error": "missing_result_contract"}

    try:
        apply_res = apply_result_contract(result_contract)
        return {
            "ok": True,
            "uploaded": True,
            "applied": True,
            "batch_id": apply_res.get("batch_id"),
            "life_events": apply_res.get("life_events"),
            "memo_ops": apply_res.get("memo_ops"),
            "changes": apply_res.get("changes"),
        }
    except Exception as e:
        msg = f"apply_failed: {type(e).__name__}: {e}"
        logger.warning(msg)
        return {"ok": False, "uploaded": True, "applied": False, "error": msg}


def sync_diary_file_to_cloud(file_path: str, *, source: str = "api_diary_save") -> Dict[str, Any]:
    """Incremental sync by file offset.

    Only unsynced bytes are sent. Watermark advances only after local apply succeeds.
    """
    p = Path(file_path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return {"ok": False, "error": f"file_not_found: {p}"}

    raw = p.read_bytes()
    total_bytes = len(raw)

    state = _get_sync_state(str(p))
    synced_bytes = int(state.get("synced_bytes") or 0)

    # File rewritten/truncated: reset watermark and full-resync.
    if synced_bytes < 0 or synced_bytes > total_bytes:
        synced_bytes = 0

    if synced_bytes == total_bytes:
        _upsert_sync_state(
            file_path=str(p),
            synced_bytes=total_bytes,
            last_file_size=total_bytes,
            source=source,
            status="up_to_date",
            error=None,
        )
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_new_content",
            "synced_bytes": synced_bytes,
            "total_bytes": total_bytes,
        }

    delta_bytes = raw[synced_bytes:]
    delta_text = delta_bytes.decode("utf-8", errors="ignore").strip()
    if not delta_text:
        # If only whitespace was appended, still advance watermark.
        _upsert_sync_state(
            file_path=str(p),
            synced_bytes=total_bytes,
            last_file_size=total_bytes,
            source=source,
            status="up_to_date",
            error=None,
        )
        return {
            "ok": True,
            "skipped": True,
            "reason": "delta_empty_after_decode",
            "synced_bytes": total_bytes,
            "total_bytes": total_bytes,
        }

    sync_res = sync_diary_text_to_cloud(delta_text, source=source)

    if bool(sync_res.get("ok")):
        _upsert_sync_state(
            file_path=str(p),
            synced_bytes=total_bytes,
            last_file_size=total_bytes,
            source=source,
            status="ok",
            error=None,
            batch_id=sync_res.get("batch_id"),
        )
        sync_res.update(
            {
                "file": str(p),
                "delta_bytes": len(delta_bytes),
                "synced_bytes": total_bytes,
                "total_bytes": total_bytes,
            }
        )
        return sync_res

    _upsert_sync_state(
        file_path=str(p),
        synced_bytes=synced_bytes,
        last_file_size=total_bytes,
        source=source,
        status="failed",
        error=str(sync_res.get("error") or "sync_failed"),
        batch_id=sync_res.get("batch_id"),
    )
    sync_res.update(
        {
            "file": str(p),
            "delta_bytes": len(delta_bytes),
            "synced_bytes": synced_bytes,
            "total_bytes": total_bytes,
        }
    )
    return sync_res


def sync_diary_file_to_cloud_bg(file_path: str, *, source: str = "api_diary_save") -> None:
    try:
        res = sync_diary_file_to_cloud(file_path, source=source)
        logger.info(
            "cloud_sync_done ok=%s file=%s synced=%s/%s skipped=%s error=%s",
            res.get("ok"),
            res.get("file"),
            res.get("synced_bytes"),
            res.get("total_bytes"),
            res.get("skipped"),
            res.get("error"),
        )
    except Exception as e:
        logger.exception(f"cloud_sync background failed: {type(e).__name__}: {e}")
