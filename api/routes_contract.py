from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pipeline.contract_apply import apply_result_contract
from pipeline.privacy_gate import build_cloud_contract_v1
from pipeline.validators import ContractValidationError

router = APIRouter()


class PrivacyGateRequest(BaseModel):
    raw_text: str
    source: str = "local_privacy_gate"
    ner_backend: Optional[str] = None
    entity_hints: Optional[Dict[str, Any]] = None


@router.post("/api/privacy/contract")
async def privacy_contract(req: PrivacyGateRequest):
    try:
        return build_cloud_contract_v1(
            raw_text=req.raw_text,
            source=req.source,
            ner_backend=req.ner_backend,
            entity_hints=req.entity_hints,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": str(e)})


class ContractApplyRequest(BaseModel):
    payload: Dict[str, Any]


@router.post("/api/contract/apply")
async def contract_apply(req: ContractApplyRequest):
    try:
        return apply_result_contract(req.payload)
    except ContractValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "CONTRACT_INVALID", "message": str(e)})
