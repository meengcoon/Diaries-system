from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from .crypto import event_digest_hex


def build_event_v1(
    *,
    device_id: str,
    group_key_version: int,
    entity_type: str,
    entity_id: str,
    op: str,
    payload: Dict[str, Any],
    deps: List[str] | None = None,
    base_version: int = 0,
    ts: int | None = None,
) -> Dict[str, Any]:
    evt = {
        "event_version": "v1",
        "device_id": str(device_id),
        "group_key_version": int(group_key_version),
        "entity_type": str(entity_type),
        "entity_id": str(entity_id),
        "op": str(op),
        "payload": payload or {},
        "deps": [str(x) for x in (deps or [])],
        "base_version": int(base_version),
        "ts": int(ts if ts is not None else time.time()),
    }
    evt["event_id"] = event_digest_hex(evt)
    return evt


def detect_conflicts(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect concurrent writes to same entity/base_version.

    Conflict rule (simple and deterministic):
    - same (entity_type, entity_id, base_version)
    - multiple distinct event_id values
    - no causal dependency path between them in deps
    """
    by_key: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = {}
    id_to_evt: Dict[str, Dict[str, Any]] = {}
    for e in events:
        eid = str(e.get("event_id") or "")
        if not eid:
            continue
        id_to_evt[eid] = e
        k = (str(e.get("entity_type") or ""), str(e.get("entity_id") or ""), int(e.get("base_version") or 0))
        by_key.setdefault(k, []).append(e)

    out: List[Dict[str, Any]] = []
    for k, rows in by_key.items():
        if len(rows) <= 1:
            continue
        ids = [str(r.get("event_id")) for r in rows if r.get("event_id")]
        if len(set(ids)) <= 1:
            continue

        # If any event depends on another sibling, treat as ordered update, not conflict.
        sibling = set(ids)
        has_order = False
        for r in rows:
            deps = set([str(x) for x in (r.get("deps") or [])])
            if deps & (sibling - {str(r.get("event_id"))}):
                has_order = True
                break
        if has_order:
            continue

        out.append(
            {
                "entity_type": k[0],
                "entity_id": k[1],
                "base_version": k[2],
                "event_ids": sorted(set(ids)),
                "reason": "concurrent_writes_same_base_version",
            }
        )
    return out
