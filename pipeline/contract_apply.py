from __future__ import annotations

from typing import Any, Dict

from .process_contract import process_contract
from .validators import validate_result_contract_v1


def apply_result_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and apply result_contract_v1 in a single DB transaction.

    The write transaction is delegated to `process_contract`, which already
    enforces atomic commit/rollback semantics.
    """
    validate_result_contract_v1(payload)
    batch_id = process_contract(payload)
    return {"ok": True, "batch_id": batch_id}
