from __future__ import annotations

from typing import Any, Dict, List

from .crypto import decrypt_json, encrypt_json


def reduce_events_to_state(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Deterministic in-memory reducer for sync events."""
    state: Dict[str, Dict[str, Any]] = {}
    for e in events:
        entity_type = str(e.get("entity_type") or "")
        entity_id = str(e.get("entity_id") or "")
        key = f"{entity_type}:{entity_id}"
        op = str(e.get("op") or "")
        payload = e.get("payload") or {}

        if op == "delete":
            state.pop(key, None)
            continue
        state[key] = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "event_id": e.get("event_id"),
            "ts": e.get("ts"),
        }
    return state


def build_checkpoint(*, events: List[Dict[str, Any]], last_seq: int) -> Dict[str, Any]:
    return {
        "checkpoint_version": "v1",
        "last_seq": int(last_seq),
        "state": reduce_events_to_state(events),
    }


def encrypt_checkpoint(*, checkpoint: Dict[str, Any], group_key: bytes, group_key_version: int) -> Dict[str, Any]:
    aad = {"kind": "checkpoint", "group_key_version": int(group_key_version)}
    box = encrypt_json(key=group_key, payload=checkpoint, aad=aad)
    return {"group_key_version": int(group_key_version), "box": box}


def decrypt_checkpoint(*, blob: Dict[str, Any], group_key: bytes) -> Dict[str, Any]:
    v = int(blob.get("group_key_version") or 0)
    box = blob.get("box") or {}
    aad = {"kind": "checkpoint", "group_key_version": v}
    return decrypt_json(key=group_key, box=box, aad=aad)
