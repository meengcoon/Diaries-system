# block_analyze.py
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from llm.ollama_client import OllamaClient

from core.settings import (
    MAX_BLOCK_CHARS,
    MIN_BLOCK_CHARS,
    PHI_MODEL,
    PHI_NUM_PREDICT,
    PROMPT_VERSION_BLOCK,
)

# Back-compat exports used by scripts (do not rename).
PROMPT_VERSION = PROMPT_VERSION_BLOCK


# Keep generation short to reduce idle-time analysis latency.
# You can override per machine / model.



class BlockInputError(ValueError):
    pass


class AnalysisValidationError(RuntimeError):
    pass


def _extract_json_object(s: str) -> str:
    if not s:
        return s
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return s.strip()
    return s[start : end + 1].strip()


def _try_repair_json_lines(s: str) -> str:
    s = s.replace("\r\n", "\n")
    cleaned: List[str] = []
    for line in s.split("\n"):
        ls = line.lstrip()
        if not ls:
            continue
        if ls.startswith("{") or ls.startswith("}"):
            cleaned.append(line)
            continue
        if ls.startswith('"') and '":' in ls:
            cleaned.append(line)
            continue
    return "\n".join(cleaned).strip()


def _coerce_signal(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 <= v <= 10 else None
    if isinstance(v, float):
        if v != v:
            return None
        return int(round(v)) if 0.0 <= v <= 10.0 else None
    if isinstance(v, str):
        m = re.search(r"(-?\d+(?:\.\d+)?)", v)
        if not m:
            return None
        try:
            num = float(m.group(1))
        except Exception:
            return None
        return int(round(num)) if 0.0 <= num <= 10.0 else None
    return None


def _normalize(obj: Dict[str, Any]) -> Dict[str, Any]:
    obj.setdefault("evidence_spans", [])
    obj.setdefault("reflection_depth", None)

    sig = obj.get("signals")
    if isinstance(sig, dict):
        for k in ("mood", "stress", "sleep", "exercise", "social", "work"):
            sig[k] = _coerce_signal(sig.get(k))

    for k in ("facts", "todos", "topics", "evidence_spans"):
        v = obj.get(k)
        if v is None:
            obj[k] = []
        elif isinstance(v, list):
            obj[k] = [str(x) for x in v if isinstance(x, (str, int, float)) and str(x).strip()]
        else:
            obj[k] = []

    if "summary_1_3" in obj and obj["summary_1_3"] is not None and not isinstance(obj["summary_1_3"], str):
        obj["summary_1_3"] = str(obj["summary_1_3"])

    rd = obj.get("reflection_depth")
    if rd is None:
        obj["reflection_depth"] = None
    elif isinstance(rd, (int, float)):
        rdi = int(round(float(rd)))
        obj["reflection_depth"] = rdi if 0 <= rdi <= 3 else None
    else:
        obj["reflection_depth"] = None

    return obj


def _validate(obj: Dict[str, Any]) -> None:
    required = ["summary_1_3", "signals", "facts", "todos", "topics"]
    missing = [k for k in required if k not in obj]
    if missing:
        raise AnalysisValidationError(f"missing keys: {missing}")

    if not isinstance(obj["summary_1_3"], str) or not obj["summary_1_3"].strip():
        raise AnalysisValidationError("summary_1_3 must be a non-empty string")

    signals = obj["signals"]
    if not isinstance(signals, dict):
        raise AnalysisValidationError("signals must be an object")

    for k in ("mood", "stress", "sleep", "exercise", "social", "work"):
        if k not in signals:
            raise AnalysisValidationError(f"missing signals.{k}")
        v = signals.get(k)
        if v is None:
            continue
        if not isinstance(v, int) or v < 0 or v > 10:
            raise AnalysisValidationError(f"signals.{k} must be int 0-10 or null")

    for k in ("facts", "todos", "topics", "evidence_spans"):
        if not isinstance(obj.get(k), list) or any(not isinstance(x, str) for x in obj.get(k, [])):
            raise AnalysisValidationError(f"{k} must be an array of strings")

    rd = obj.get("reflection_depth")
    if rd is not None and (not isinstance(rd, int) or rd < 0 or rd > 3):
        raise AnalysisValidationError("reflection_depth must be int 0-3 or null")


def _build_messages(*, title: str | None, raw_text: str) -> List[Dict[str, str]]:
    template = {
        "summary_1_3": "",
        "signals": {"mood": None, "stress": None, "sleep": None, "exercise": None, "social": None, "work": None},
        "facts": [],
        "todos": [],
        "topics": [],
        "evidence_spans": [],
        "reflection_depth": None,
    }

    sys = (
        "You are a strict JSON extraction engine. "
        "Return ONE single JSON object ONLY. No markdown, no code fences, no commentary. "
        "Output must be valid JSON and must keep keys exactly as in TEMPLATE. "
        "No extra keys. facts/todos/topics/evidence_spans are arrays of strings. "
        "signal scores are int 0-10 or null. reflection_depth is int 0-3 or null."
    )

    header = f"TITLE: {(title or '').strip()}\n" if (title or "").strip() else ""
    user = (
        "Fill TEMPLATE using ONLY the DIARY BLOCK.\n"
        f"TEMPLATE: {json.dumps(template, ensure_ascii=False)}\n\n"
        "DIARY BLOCK:\n"
        f"{header}{raw_text.strip()}\n"
    )

    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _build_fix_messages(bad_output: str) -> List[Dict[str, str]]:
    sys = (
        "You are a JSON repair engine. Rewrite into ONE valid JSON object ONLY. "
        "No markdown, no commentary, no extra keys. Keep the required keys and types."
    )
    user = "BAD OUTPUT:\n" + (bad_output or "")
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _parse_or_raise(raw: str) -> Dict[str, Any]:
    cand = _extract_json_object(raw)
    try:
        obj = json.loads(cand)
    except Exception:
        repaired = _try_repair_json_lines(cand)
        try:
            obj = json.loads(repaired)
        except Exception as e:
            raise AnalysisValidationError(f"non-JSON output: {e}") from e

    if not isinstance(obj, dict):
        raise AnalysisValidationError("top-level must be an object")

    obj = _normalize(obj)
    _validate(obj)
    return obj


@dataclass
class BlockAnalyzeResult:
    analysis: Dict[str, Any]
    ms: int
    raw_output: str


async def analyze_block(*, title: str | None, raw_text: str, client: OllamaClient) -> BlockAnalyzeResult:
    text = (raw_text or "").strip()
    if len(text) < MIN_BLOCK_CHARS:
        raise BlockInputError(f"block too short: {len(text)} chars")
    if len(text) > MAX_BLOCK_CHARS:
        raise BlockInputError(f"block too long: {len(text)} chars (max {MAX_BLOCK_CHARS})")

    msgs = _build_messages(title=title, raw_text=text)
    out1, ms1 = await client.chat_text(
        model=PHI_MODEL,
        messages=msgs,
        options={"temperature": 0, "top_p": 0.1, "num_predict": PHI_NUM_PREDICT},
    )

    try:
        obj = _parse_or_raise(out1)
        return BlockAnalyzeResult(analysis=obj, ms=ms1, raw_output=out1)
    except AnalysisValidationError:
        fix_msgs = _build_fix_messages(out1)
        out2, ms2 = await client.chat_text(
            model=PHI_MODEL,
            messages=fix_msgs,
            options={"temperature": 0, "top_p": 0.1, "num_predict": PHI_NUM_PREDICT},
        )
        obj2 = _parse_or_raise(out2)
        return BlockAnalyzeResult(analysis=obj2, ms=(ms1 + ms2), raw_output=out2)
