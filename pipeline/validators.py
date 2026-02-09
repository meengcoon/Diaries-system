from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from storage.db_core import connect


class ContractValidationError(ValueError):
    pass


def _require_dict(v: Any, *, where: str) -> Dict[str, Any]:
    if not isinstance(v, dict):
        raise ContractValidationError(f"{where} must be object")
    return v


def _require_list(v: Any, *, where: str) -> List[Any]:
    if not isinstance(v, list):
        raise ContractValidationError(f"{where} must be array")
    return v


def _require_int(v: Any, *, where: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ContractValidationError(f"{where} must be integer")
    return int(v)


def _parse_block_ref(ref: str) -> int:
    s = str(ref or "").strip()
    if ":" not in s:
        raise ContractValidationError(f"invalid evidence ref: {s!r}")
    prefix, suffix = s.split(":", 1)
    if prefix != "block":
        raise ContractValidationError(f"unsupported evidence ref prefix: {prefix!r}")
    try:
        block_id = int(suffix)
    except Exception:
        raise ContractValidationError(f"invalid block ref id: {s!r}")
    if block_id <= 0:
        raise ContractValidationError(f"invalid block ref id: {s!r}")
    return block_id


def _block_exists(conn, block_id: int) -> bool:
    row = conn.execute("SELECT 1 FROM entry_blocks WHERE block_id=? LIMIT 1", (int(block_id),)).fetchone()
    return bool(row)


def validate_result_contract_v1(payload: Dict[str, Any], *, now_ts: Optional[int] = None) -> None:
    """Validate a result_contract_v1 payload against local invariants.

    Hard checks:
    - schema basics
    - event_ts not in future
    - evidence_refs must be block:* and point to existing local entry_blocks.block_id
    """

    obj = _require_dict(payload, where="payload")
    version = str(obj.get("contract_version") or "").strip()
    if version != "v1":
        raise ContractValidationError(f"unsupported contract_version: {version!r}")

    blocks = _require_list(obj.get("blocks"), where="payload.blocks")
    if not blocks:
        raise ContractValidationError("payload.blocks is empty")

    now_s = int(now_ts if now_ts is not None else time.time())
    conn = connect()
    try:
        for i, b in enumerate(blocks):
            bd = _require_dict(b, where=f"blocks[{i}]")
            event_ts = _require_int(bd.get("event_ts"), where=f"blocks[{i}].event_ts")
            if event_ts <= 0:
                raise ContractValidationError(f"blocks[{i}].event_ts must be > 0")
            if event_ts > now_s:
                raise ContractValidationError(
                    f"future event_ts is not allowed: blocks[{i}].event_ts={event_ts} now={now_s}"
                )

            evidence = bd.get("evidence_refs")
            if evidence is None:
                continue

            refs = _require_list(evidence, where=f"blocks[{i}].evidence_refs")
            for j, item in enumerate(refs):
                if isinstance(item, str):
                    ref = item
                    ts = None
                else:
                    ed = _require_dict(item, where=f"blocks[{i}].evidence_refs[{j}]")
                    ref = str(ed.get("ref") or "").strip()
                    ts = ed.get("ts")

                block_id = _parse_block_ref(ref)
                if not _block_exists(conn, block_id):
                    raise ContractValidationError(f"evidence ref not found: {ref}")

                if ts is not None:
                    ev_ts = _require_int(ts, where=f"blocks[{i}].evidence_refs[{j}].ts")
                    if ev_ts > now_s:
                        raise ContractValidationError(
                            f"future evidence ts is not allowed: ref={ref} ts={ev_ts} now={now_s}"
                        )
                    if ev_ts > event_ts:
                        raise ContractValidationError(
                            f"evidence ts beyond event_ts: ref={ref} ts={ev_ts} event_ts={event_ts}"
                        )
    finally:
        conn.close()
