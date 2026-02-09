from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any, Dict, List


def _mk_blocks(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    facts = contract.get("facts") or []
    if not isinstance(facts, list):
        facts = []
    summary = " ".join([str(x).strip() for x in facts[:2] if str(x).strip()]) or "No summary"
    tags = contract.get("tags") or []
    if not isinstance(tags, list):
        tags = []

    block_refs = contract.get("block_refs") or []
    if not isinstance(block_refs, list):
        block_refs = []

    return [
        {
            "block_id": f"le:{uuid.uuid4().hex[:8]}",
            "event_ts": int(time.time()),
            "event_type": "cloud_analysis",
            "summary": summary[:512],
            "tags": [str(t) for t in tags[:8]],
            "evidence_refs": [{"ref": str(r), "ts": int(time.time())} for r in block_refs[:16]],
            "memo_ops": [],
        }
    ]


def run_analysis(contract: Dict[str, Any]) -> Dict[str, Any]:
    """Stateless cloud analysis entry.

    Important operational rules (deployment-side):
    - Do not persist request payloads.
    - Keep process ephemeral.
    """
    return {
        "contract_version": "v1",
        "source": "cloud_runner",
        "model_provider": "local_stub",
        "model_name": "analysis_runner_v1",
        "blocks": _mk_blocks(contract),
    }


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"error": "empty input"}))
        return 1
    payload = json.loads(raw)
    out = run_analysis(payload)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
