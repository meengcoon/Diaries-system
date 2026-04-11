from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from storage.repo_chat import list_recent_chat_messages
from storage.repo_entries import list_recent_entry_summaries
from storage.repo_mem import list_mem_cards


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text) if text else None
    except Exception:
        return None


def build_self_profile_pack(*, char_budget: int = 3000) -> Dict[str, Any]:
    recent_rows = list_recent_entry_summaries(12)
    chat_rows = list_recent_chat_messages(limit=12, role="user")
    mem_rows = list_mem_cards(limit=10)

    recent = []
    for row in recent_rows:
        summary = str(row.get("summary_1_3") or "").strip()
        if not summary or summary == "Summary not provided":
            continue
        recent.append(
            {
                "entry_id": row.get("entry_id"),
                "created_at": row.get("created_at"),
                "summary": summary[:240],
                "topics": row.get("topics") or [],
                "signals": row.get("signals") or {},
            }
        )
        if len(recent) >= 6:
            break

    memories = []
    for row in mem_rows:
        content = _safe_json_loads(str(row.get("content_json") or "")) or {}
        if not isinstance(content, dict):
            content = {}
        topics = content.get("topics") or []
        last_summary = str(content.get("last_summary") or "").strip()
        nested = content.get("content") if isinstance(content.get("content"), dict) else {}
        nested_summary = str(nested.get("last_summary") or "").strip() if isinstance(nested, dict) else ""
        summary = last_summary or nested_summary
        memories.append(
            {
                "card_id": row.get("card_id"),
                "type": row.get("type"),
                "confidence": row.get("confidence"),
                "topics": topics[:5] if isinstance(topics, list) else [],
                "last_summary": summary[:240],
            }
        )
        if len(memories) >= 5:
            break

    recent_chat = []
    for row in chat_rows:
        text = str(row.get("text") or "").strip()
        if not text or len(text) < 4:
            continue
        recent_chat.append(
            {
                "message_id": row.get("id"),
                "created_at": row.get("created_at"),
                "text": text[:180],
            }
        )
        if len(recent_chat) >= 6:
            break

    return {
        "schema": "self_profile_pack_v3",
        "query": "self_profile",
        "limits": {"char_budget": int(char_budget)},
        "self_profile": {
            "recent_summaries": recent,
            "recent_chat_messages": recent_chat,
            "memory_cards": memories,
        },
        "recent": recent,
        "topk": [],
        "mem_cards": memories,
        "meta": {
            "build_ms": 0,
            "truncated": False,
            "steps": [],
            "initial_counts": {
                "recent": len(recent),
                "topk": 0,
                "mem_cards": len(memories),
                "snapshots": 0,
            },
        },
    }


def fallback_self_profile_answer(pack: Dict[str, Any], *, lang: str) -> str:
    profile = pack.get("self_profile") if isinstance(pack.get("self_profile"), dict) else {}
    recent = profile.get("recent_summaries") if isinstance(profile, dict) else []
    recent_chat = profile.get("recent_chat_messages") if isinstance(profile, dict) else []
    memories = profile.get("memory_cards") if isinstance(profile, dict) else []
    snapshot_summary = ""
    snapshot_traits: List[str] = []
    for row in memories if isinstance(memories, list) else []:
        if not isinstance(row, dict):
            continue
        for item in row.get("topics") or []:
            text = str(item or "").strip()
            if text and text not in snapshot_traits:
                snapshot_traits.append(text)
    if lang == "zh" and (snapshot_summary or snapshot_traits):
        recent_summary = ""
        for item in recent if isinstance(recent, list) else []:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("summary") or "").strip()
            if candidate:
                recent_summary = candidate
                break
        parts = [recent_summary] if recent_summary else []
        if snapshot_traits:
            parts.append("比较稳定的特征包括：" + "、".join(snapshot_traits[:3]))
        return "；".join(parts) + "。这是一份基于近期和长期记录汇总的阶段性画像，不是绝对定论。"
    texts: List[str] = []
    for item in recent if isinstance(recent, list) else []:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        if summary:
            texts.append(summary.lower())
    for item in memories if isinstance(memories, list) else []:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("last_summary") or "").strip()
        if summary:
            texts.append(summary.lower())
    for item in recent_chat if isinstance(recent_chat, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            texts.append(text.lower())

    joined = "\n".join(texts)
    if not joined.strip():
        return ""

    traits_zh: List[str] = []
    if re.search(r"\bwork\b|工作|上班|下班", joined):
        traits_zh.append("你会留意工作节奏和一天安排，对效率变化比较敏感。")
    if re.search(r"\bsleep\b|睡|补觉|休息", joined):
        traits_zh.append("你的状态明显会受休息和睡眠影响，这也是你记录里反复出现的线索。")
    if re.search(r"\bfocus\b|library|专注|图书馆|效率", joined):
        traits_zh.append("当状态不理想时，你会主动想办法换环境、把注意力拉回来。")
    if re.search(r"unmotivated|没动力|疲惫|累|低落", joined):
        traits_zh.append("你会比较诚实地记录自己没动力、疲惫或状态下滑的时候。")
    if re.search(r"hair|发型|头发|外形|服务", joined):
        traits_zh.append("你对体验细节和结果感受有自己的判断，不太会敷衍带过。")

    if not traits_zh:
        summaries = [t for t in texts if t][:2]
        if not summaries:
            return ""
        if lang == "zh":
            return "基于你最近的日记，我暂时只能看出你会持续记录自己的日常状态和感受，但稳定特征证据还不够多。"
        return "From your recent diary, I can only tell that you consistently record your daily state and feelings, but there is not enough evidence yet for stronger trait claims."

    if lang == "zh":
        head = "基于你现有日记，我对你的阶段性印象是："
        tail = "这更像是近期状态总结，不是最终的人格定论。"
        body = "；".join([x.rstrip("。； ") for x in traits_zh[:3]])
        if len(memories if isinstance(memories, list) else []) < 3:
            tail = "目前长期记忆卡还不多，所以这更像近期印象，不是稳定人格结论。"
        return f"{head}{body}。{tail}"

    return ""
