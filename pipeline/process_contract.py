from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# NOTE: Keep this module dependency-light. It is part of the ingestion path.
try:
    from storage.db_core import connect
except Exception:  # pragma: no cover
    # Some older layouts re-exported connect elsewhere.
    from storage.db import connect  # type: ignore


class ContractValidationError(ValueError):
    """Raised when contract payload fails gatekeeping."""


# ----------------------------
# Contract constraints (v1)
# ----------------------------

# Field limits: defensive. Keep tight to avoid prompt leakage into DB.
MAX_BLOCK_ID_LEN = 128
MAX_EVENT_ID_LEN = 128
MAX_EVENT_TYPE_LEN = 64
MAX_SUMMARY_LEN = 1024
MAX_TAG_LEN = 64
MAX_TAGS = 64

MAX_CARD_KEY_LEN = 128
MAX_OP_ID_LEN = 128
MAX_OP_TYPE_LEN = 32


ALLOWED_REF_PREFIXES: Set[str] = {
    # Internal refs
    "entry",   # entries.id
    "block",   # entry_blocks.id
    "le",      # life_events.block_id or event_id (v1 uses le:* for block_id)
    "mc",      # memo_cards.card_key
    "op",      # memo_ops.op_id
    # External/opaque refs (existence check not enforced)
    "url",
    "text",
    "note",
}

ALLOWED_MEMO_OP_TYPES: Set[str] = {
    # Keep small; widen later when the contract is versioned.
    "upsert",
    "delete",
    "merge",
    "patch",
    "noop",
}


@dataclass(frozen=True)
class _EvidenceRef:
    ref: str
    ts: Optional[int] = None


def _now_ts() -> int:
    return int(time.time())


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json_dumps(obj: Any) -> str:
    # Compact JSON to reduce DB size.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _require_dict(x: Any, *, where: str) -> Dict[str, Any]:
    if not isinstance(x, dict):
        raise ContractValidationError(f"{where} must be an object")
    return x


def _require_list(x: Any, *, where: str) -> List[Any]:
    if x is None:
        return []
    if not isinstance(x, list):
        raise ContractValidationError(f"{where} must be an array")
    return x


def _require_str(x: Any, *, where: str, max_len: int, allow_empty: bool = False) -> str:
    if not isinstance(x, str):
        raise ContractValidationError(f"{where} must be a string")
    s = x.strip()
    if not allow_empty and not s:
        raise ContractValidationError(f"{where} must be non-empty")
    if len(s) > max_len:
        raise ContractValidationError(f"{where} too long: {len(s)} > {max_len}")
    return s


def _require_int(x: Any, *, where: str, min_value: Optional[int] = None) -> int:
    if isinstance(x, bool) or not isinstance(x, int):
        raise ContractValidationError(f"{where} must be an integer")
    if min_value is not None and x < min_value:
        raise ContractValidationError(f"{where} must be >= {min_value}")
    return int(x)


def _normalize_tags(tags: Any) -> List[str]:
    arr = _require_list(tags, where="block.tags")
    if len(arr) > MAX_TAGS:
        raise ContractValidationError(f"block.tags too many: {len(arr)} > {MAX_TAGS}")
    out: List[str] = []
    for i, t in enumerate(arr):
        s = _require_str(t, where=f"block.tags[{i}]", max_len=MAX_TAG_LEN, allow_empty=False)
        out.append(s)
    return out


def _parse_ref_prefix(ref: str) -> Tuple[str, str]:
    if ":" not in ref:
        raise ContractValidationError(f"evidence_refs.ref invalid (missing prefix): {ref!r}")
    prefix, rest = ref.split(":", 1)
    prefix = prefix.strip()
    rest = rest.strip()
    if prefix not in ALLOWED_REF_PREFIXES:
        raise ContractValidationError(f"evidence_refs.ref unsupported prefix: {prefix!r}")
    if not rest:
        raise ContractValidationError(f"evidence_refs.ref invalid (empty suffix): {ref!r}")
    return prefix, rest


def _normalize_evidence_refs(evidence_refs: Any) -> List[_EvidenceRef]:
    arr = _require_list(evidence_refs, where="block.evidence_refs")
    out: List[_EvidenceRef] = []
    for i, item in enumerate(arr):
        if isinstance(item, str):
            ref = _require_str(item, where=f"evidence_refs[{i}]", max_len=256, allow_empty=False)
            _parse_ref_prefix(ref)
            out.append(_EvidenceRef(ref=ref, ts=None))
            continue

        if isinstance(item, dict):
            ref = _require_str(item.get("ref"), where=f"evidence_refs[{i}].ref", max_len=256, allow_empty=False)
            _parse_ref_prefix(ref)
            ts_raw = item.get("ts")
            ts = None
            if ts_raw is not None:
                ts = _require_int(ts_raw, where=f"evidence_refs[{i}].ts", min_value=0)
            out.append(_EvidenceRef(ref=ref, ts=ts))
            continue

        raise ContractValidationError(f"evidence_refs[{i}] must be string or object")
    return out


def _validate_evidence_chain(
    *,
    conn,
    event_ts: int,
    evidence_refs: List[_EvidenceRef],
    known_block_ids: Set[str],
    known_event_ids: Set[str],
    known_op_ids: Set[str],
    now_ts: int,
) -> None:
    """Gatekeeping rules:

    - Ref routing: prefix in ALLOWED_REF_PREFIXES
    - Existence: for internal refs (entry/block/le/op/mc) ensure exists in payload or DB
    - Time: if evidence.ts is provided, must be <= now AND <= event_ts
    """

    for ev in evidence_refs:
        prefix, suffix = _parse_ref_prefix(ev.ref)

        if ev.ts is not None:
            if ev.ts > now_ts:
                raise ContractValidationError(f"future evidence is not allowed: {ev.ref} ts={ev.ts} now={now_ts}")
            if ev.ts > event_ts:
                raise ContractValidationError(
                    f"evidence time travels beyond event_ts: {ev.ref} ts={ev.ts} event_ts={event_ts}"
                )

        # External refs are accepted without existence checks.
        if prefix in {"url", "text", "note"}:
            continue

        # Internal existence checks.
        if prefix == "le":
            # v1 supports both life_events.block_id (le:*) and event_id.
            if ev.ref in known_block_ids or suffix in known_event_ids:
                continue
            row = conn.execute(
                "SELECT 1 FROM life_events WHERE block_id=? OR event_id=? LIMIT 1",
                (ev.ref, suffix),
            ).fetchone()
            if not row:
                raise ContractValidationError(f"evidence ref not found: {ev.ref}")
            continue

        if prefix == "op":
            if suffix in known_op_ids:
                continue
            row = conn.execute("SELECT 1 FROM memo_ops WHERE op_id=? LIMIT 1", (suffix,)).fetchone()
            if not row:
                raise ContractValidationError(f"evidence ref not found: {ev.ref}")
            continue

        if prefix == "mc":
            row = conn.execute("SELECT 1 FROM memo_cards WHERE card_key=? LIMIT 1", (ev.ref,)).fetchone()
            if not row:
                raise ContractValidationError(f"evidence ref not found: {ev.ref}")
            continue

        if prefix == "entry":
            # entries.id is INTEGER
            try:
                entry_id = int(suffix)
            except Exception:
                raise ContractValidationError(f"evidence ref invalid entry id: {ev.ref}")
            row = conn.execute("SELECT 1 FROM entries WHERE id=? LIMIT 1", (entry_id,)).fetchone()
            if not row:
                raise ContractValidationError(f"evidence ref not found: {ev.ref}")
            continue

        if prefix == "block":
            try:
                block_id = int(suffix)
            except Exception:
                raise ContractValidationError(f"evidence ref invalid block id: {ev.ref}")
            row = conn.execute("SELECT 1 FROM entry_blocks WHERE block_id=? LIMIT 1", (block_id,)).fetchone()
            if not row:
                raise ContractValidationError(f"evidence ref not found: {ev.ref}")
            continue


def _ensure_contract_schema(conn) -> None:
    """Ensure schema_v2.sql is applied (batches/life_events/memo_ops/changes/memo_cards).

    This project keeps contract tables in schema_v2.sql (not in init_db()).
    We defensively apply it if batches table is missing.
    """

    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batches' LIMIT 1"
    ).fetchone()
    if row:
        return

    root = Path(__file__).resolve().parents[1]
    schema_path = root / "schema_v2.sql"
    if not schema_path.exists():
        raise RuntimeError("schema_v2.sql not found; cannot ingest cloud contract")

    conn.executescript(schema_path.read_text(encoding="utf-8"))


def trigger_rag_rebuild_stub(*, batch_id: str) -> None:
    """Stub for post-commit rebuild.

    Replace with a job-queue enqueue (preferred) or an async task runner.
    MUST be called only after COMMIT.
    """

    # Intentionally a no-op.
    return


def process_contract(payload: Dict[str, Any]) -> str:
    """Ingest a cloud_contract_v1-like payload.

    Expected shape (minimal):
    {
      "contract_version": "v1",
      "source": "cloud",
      "model_provider": "...",
      "model_name": "...",
      "blocks": [
        {
          "block_id": "le:1",
          "event_ts": 123,
          "event_type": "...",
          "summary": "...",
          "tags": ["..."],
          "evidence_refs": [ {"ref":"url:...", "ts": 123} ],
          "memo_ops": [
            {"card_key":"mc:...", "op_type":"upsert", "payload":{...}, "evidence_refs":[]}
          ]
        }
      ]
    }

    Returns: batch_id
    """

    payload = _require_dict(payload, where="payload")

    contract_version = str(payload.get("contract_version") or "v1").strip()
    if contract_version != "v1":
        raise ContractValidationError(f"unsupported contract_version: {contract_version!r}")

    model_provider = (payload.get("model_provider") or None)
    model_name = (payload.get("model_name") or None)
    source = (payload.get("source") or "cloud")

    blocks = _require_list(payload.get("blocks"), where="payload.blocks")
    if not blocks:
        raise ContractValidationError("payload.blocks is empty")

    # Pre-scan IDs to validate intra-payload evidence routing.
    known_block_ids: Set[str] = set()
    known_event_ids: Set[str] = set()
    known_op_ids: Set[str] = set()
    for i, b in enumerate(blocks):
        bd = _require_dict(b, where=f"blocks[{i}]")
        block_id = _require_str(bd.get("block_id"), where=f"blocks[{i}].block_id", max_len=MAX_BLOCK_ID_LEN)
        known_block_ids.add(block_id)
        ev_id_raw = bd.get("event_id")
        if isinstance(ev_id_raw, str) and ev_id_raw.strip():
            known_event_ids.add(ev_id_raw.strip())
        for j, op in enumerate(_require_list(bd.get("memo_ops"), where=f"blocks[{i}].memo_ops")):
            od = _require_dict(op, where=f"blocks[{i}].memo_ops[{j}]")
            op_id_raw = od.get("op_id")
            if isinstance(op_id_raw, str) and op_id_raw.strip():
                known_op_ids.add(op_id_raw.strip())

    batch_id = _new_id("batch")
    now_ts = _now_ts()

    conn = connect()
    try:
        _ensure_contract_schema(conn)

        # IMPORTANT: must be a single transaction.
        conn.execute("BEGIN;")

        conn.execute(
            "INSERT INTO batches(batch_id, contract_version, model_provider, model_name, source) "
            "VALUES(?, ?, ?, ?, ?)",
            (batch_id, contract_version, model_provider, model_name, str(source)),
        )

        for i, b in enumerate(blocks):
            bd = _require_dict(b, where=f"blocks[{i}]")

            block_id = _require_str(bd.get("block_id"), where=f"blocks[{i}].block_id", max_len=MAX_BLOCK_ID_LEN)
            event_id = bd.get("event_id")
            if isinstance(event_id, str) and event_id.strip():
                event_id = _require_str(event_id, where=f"blocks[{i}].event_id", max_len=MAX_EVENT_ID_LEN)
            else:
                # Stable enough for audit; unique across this batch.
                event_id = _new_id("e")

            event_ts = _require_int(bd.get("event_ts"), where=f"blocks[{i}].event_ts", min_value=1)
            event_type = _require_str(
                bd.get("event_type"), where=f"blocks[{i}].event_type", max_len=MAX_EVENT_TYPE_LEN
            )

            summary = bd.get("summary")
            if summary is not None:
                summary = _require_str(summary, where=f"blocks[{i}].summary", max_len=MAX_SUMMARY_LEN, allow_empty=True)
            else:
                summary = None

            tags = _normalize_tags(bd.get("tags"))
            evidence = _normalize_evidence_refs(bd.get("evidence_refs"))

            _validate_evidence_chain(
                conn=conn,
                event_ts=event_ts,
                evidence_refs=evidence,
                known_block_ids=known_block_ids,
                known_event_ids=known_event_ids,
                known_op_ids=known_op_ids,
                now_ts=now_ts,
            )

            confidence = bd.get("confidence")
            if confidence is None:
                confidence = 0.5
            try:
                confidence_f = float(confidence)
            except Exception:
                raise ContractValidationError(f"blocks[{i}].confidence must be number")
            if not (0.0 <= confidence_f <= 1.0):
                raise ContractValidationError(f"blocks[{i}].confidence out of range: {confidence_f}")

            # Write life_events
            conn.execute(
                "INSERT INTO life_events(event_id,batch_id,block_id,event_ts,event_type,summary,tags,evidence_refs,confidence) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    str(event_id),
                    batch_id,
                    block_id,
                    event_ts,
                    event_type,
                    summary,
                    _json_dumps(tags),
                    _json_dumps([ev.__dict__ for ev in evidence]),
                    confidence_f,
                ),
            )

            # Audit change: life_events create
            conn.execute(
                "INSERT INTO changes(change_id,batch_id,entity_type,entity_id,action,diff_json) "
                "VALUES(?,?,?,?,?,?)",
                (
                    _new_id("ch"),
                    batch_id,
                    "life_events",
                    str(event_id),
                    "create",
                    "{}",
                ),
            )

            # Write memo_ops (optional)
            memo_ops = _require_list(bd.get("memo_ops"), where=f"blocks[{i}].memo_ops")
            for j, op in enumerate(memo_ops):
                od = _require_dict(op, where=f"blocks[{i}].memo_ops[{j}]")
                op_id = od.get("op_id")
                if isinstance(op_id, str) and op_id.strip():
                    op_id = _require_str(op_id, where=f"blocks[{i}].memo_ops[{j}].op_id", max_len=MAX_OP_ID_LEN)
                else:
                    op_id = _new_id("op")

                card_key = _require_str(
                    od.get("card_key"),
                    where=f"blocks[{i}].memo_ops[{j}].card_key",
                    max_len=MAX_CARD_KEY_LEN,
                )
                op_type = _require_str(
                    od.get("op_type"),
                    where=f"blocks[{i}].memo_ops[{j}].op_type",
                    max_len=MAX_OP_TYPE_LEN,
                )
                if op_type not in ALLOWED_MEMO_OP_TYPES:
                    raise ContractValidationError(
                        f"blocks[{i}].memo_ops[{j}].op_type unsupported: {op_type!r}"
                    )

                payload_json = od.get("payload")
                if not isinstance(payload_json, (dict, list)):
                    raise ContractValidationError(f"blocks[{i}].memo_ops[{j}].payload must be object/array")

                op_evidence = _normalize_evidence_refs(od.get("evidence_refs"))
                _validate_evidence_chain(
                    conn=conn,
                    event_ts=event_ts,
                    evidence_refs=op_evidence,
                    known_block_ids=known_block_ids,
                    known_event_ids=known_event_ids,
                    known_op_ids=known_op_ids,
                    now_ts=now_ts,
                )

                conn.execute(
                    "INSERT INTO memo_ops(op_id,batch_id,card_key,op_type,payload_json,evidence_refs) "
                    "VALUES(?,?,?,?,?,?)",
                    (
                        str(op_id),
                        batch_id,
                        card_key,
                        op_type,
                        _json_dumps(payload_json),
                        _json_dumps([ev.__dict__ for ev in op_evidence]),
                    ),
                )

                conn.execute(
                    "INSERT INTO changes(change_id,batch_id,entity_type,entity_id,action,diff_json) "
                    "VALUES(?,?,?,?,?,?)",
                    (
                        _new_id("ch"),
                        batch_id,
                        "memo_ops",
                        str(op_id),
                        "create",
                        "{}",
                    ),
                )

        conn.commit()

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    # Post-commit hook (stub for now)
    trigger_rag_rebuild_stub(batch_id=batch_id)
    return batch_id
