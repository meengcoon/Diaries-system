from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from storage.db import get_mem_card, upsert_mem_card


CARD_ID = "chat_profile:general"
CARD_TYPE = "chat_profile"

_STOPWORDS = {
    "我", "我的", "我们", "你", "你的", "你们", "是", "会", "都", "就", "又", "很", "还", "也",
    "一个", "这个", "那个", "最近", "现在", "自己", "东西", "事情", "内容", "问题",
    "the", "and", "for", "with", "that", "this", "have", "from", "about",
}


def _safe_json_loads(text: str) -> Any:
    try:
        import json

        return json.loads(text) if text else None
    except Exception:
        return None


def _extract_phrase(text: str, pattern: str, max_len: int = 40) -> Optional[str]:
    m = re.search(pattern, text, flags=re.I)
    if not m:
        return None
    raw = str(m.group(1) or "").strip(" ，。！？,.!?;；:")
    raw = re.sub(r"\s+", " ", raw)
    if not raw:
        return None
    return raw[:max_len]


def _extract_topics(text: str) -> List[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{1,6}|[a-zA-Z][a-zA-Z0-9_-]{2,}", text or "")
    out: List[str] = []
    for tok in tokens:
        if tok.lower() in _STOPWORDS or tok in _STOPWORDS:
            continue
        if tok not in out:
            out.append(tok)
        if len(out) >= 8:
            break
    return out


def extract_chat_memory_observations(text: str) -> List[Dict[str, str]]:
    raw = str(text or "").strip()
    if not raw:
        return []
    if not re.search(r"\bI\b|我|我的|自己", raw, flags=re.I):
        return []

    obs: List[Dict[str, str]] = []

    like = _extract_phrase(raw, r"我(?:比较)?喜欢([^，。！？,.!?；;]+)")
    if like:
        obs.append({"kind": "preference", "text": f"喜欢 {like}"})

    dislike = _extract_phrase(raw, r"我(?:不喜欢|讨厌)([^，。！？,.!?；;]+)")
    if dislike:
        obs.append({"kind": "preference", "text": f"不喜欢 {dislike}"})

    plan = _extract_phrase(raw, r"我(?:想要|打算|准备|计划|希望)([^，。！？,.!?；;]+)")
    if plan:
        obs.append({"kind": "plan", "text": f"计划 {plan}"})

    trait = _extract_phrase(raw, r"我(?:总是|经常|容易|不太会|不太能|很难)([^，。！？,.!?；;]+)")
    if trait:
        obs.append({"kind": "trait", "text": f"常见模式 {trait}"})

    state = _extract_phrase(raw, r"我(?:最近|现在)([^，。！？,.!?；;]+)")
    if state:
        obs.append({"kind": "state", "text": f"近期状态 {state}"})

    concern = None
    if re.search(r"我是不是|你觉得我|你对我的认知|你有我哪些信息|我是什么样的人", raw):
        concern = raw[:80]
    if concern:
        obs.append({"kind": "concern", "text": concern})

    dedup: List[Dict[str, str]] = []
    seen = set()
    for item in obs:
        key = (item.get("kind"), item.get("text"))
        if key in seen or not item.get("text"):
            continue
        seen.add(key)
        dedup.append(item)
    return dedup


def update_chat_memory(*, message_id: int, user_text: str, created_at: Optional[str] = None) -> Dict[str, Any]:
    observations = extract_chat_memory_observations(user_text)
    if not observations:
        return {"updated": False, "card_id": None, "observations": []}

    row = get_mem_card(CARD_ID)
    content = _safe_json_loads(str(row.get("content_json") or "")) if row else {}
    if not isinstance(content, dict):
        content = {}

    existing = content.get("observations") if isinstance(content.get("observations"), list) else []
    merged: List[Dict[str, Any]] = []
    seen = set()
    for item in existing + observations:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        key = (kind, text)
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "kind": kind or "note",
                "text": text,
                "source": "chat",
                "message_id": int(item.get("message_id") or message_id),
            }
        )

    topics = list(dict.fromkeys((content.get("topics") or []) + _extract_topics(user_text)))[:12]
    new_content = {
        "topics": topics,
        "source": "chat",
        "last_message_id": int(message_id),
        "last_user_text": str(user_text or "").strip()[:240],
        "observations": merged[-30:],
    }
    confidence = 0.55 if len(new_content["observations"]) < 4 else 0.7
    upsert_mem_card(
        card_id=CARD_ID,
        type=CARD_TYPE,
        content_json=new_content,
        updated_at=created_at,
        confidence=confidence,
    )
    return {"updated": True, "card_id": CARD_ID, "observations": observations}
