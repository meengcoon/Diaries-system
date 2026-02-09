# bot/cascade_bot.py
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

try:
    from bot.generation_router import generate as routed_generate
except Exception:  # pragma: no cover
    routed_generate = None  # type: ignore

from core.settings import PHI_MODEL as DEFAULT_PHI_MODEL, PHI_NUM_PREDICT, QWEN_MODEL as DEFAULT_QWEN_MODEL
from llm.ollama_client import OllamaClient
from llm.providers import ProviderError, ProviderResult
from pipeline.context_pack import build_context_pack, build_context_pack_text

ROUTE_PROMPT_VERSION = "phi_route_v1"
ANSWER_PROMPT_VERSION = "qwen_grounded_answer_v1"

# Per-model hard timeouts (seconds)
PHI_TIMEOUT_S = float(os.getenv("PHI_TIMEOUT_S", "12"))
QWEN_TIMEOUT_S = float(os.getenv("QWEN_TIMEOUT_S", "45"))

# Total request budget (seconds) to avoid hitting client-side curl max-time
TOTAL_TIMEOUT_S = float(os.getenv("TOTAL_TIMEOUT_S", "70"))

# Output limits (Ollama num_predict)
QWEN_NUM_PREDICT = int(os.getenv("QWEN_NUM_PREDICT", "420"))

logger = logging.getLogger(__name__)


def _extract_first_json_obj(text: str) -> str:
    if not text:
        return text
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return text.strip()
    return text[s : e + 1].strip()


def _detect_lang(text: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", text or "") else "en"


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        iv = int(v)
    except Exception:
        return int(default)
    return max(int(lo), min(int(hi), int(iv)))


def _fallback_query(user_text: str) -> str:
    """Deterministic, small keyword query when Phi routing fails."""
    t = (user_text or "").strip().lower()
    if not t:
        return ""

    topic_map = [
        (r"\b(sleep|slept|insomnia|nap)\b|睡|失眠", "sleep"),
        (r"\b(work|job|shift|meeting|deadline)\b|工作|上班|班", "work"),
        (r"\b(gym|workout|run|running|exercise|training)\b|运动|健身|跑", "exercise"),
        (r"\b(friend|friends|social|party|date)\b|朋友|社交|聚会|约会", "social"),
        (r"\b(stress|anxious|anxiety|panic)\b|压力|焦虑", "stress"),
    ]
    for pat, tag in topic_map:
        if re.search(pat, t):
            return tag

    tokens = re.findall(r"[\u4e00-\u9fff]{1,6}|[a-z0-9]{2,}", t)
    stop = {
        "the",
        "a",
        "an",
        "to",
        "of",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "in",
        "on",
        "for",
        "with",
        "我",
        "你",
        "他",
        "她",
        "它",
        "我们",
        "你们",
        "他们",
        "什么",
        "怎么",
        "为什么",
        "是否",
        "今天",
        "昨天",
        "明天",
    }
    out: List[str] = []
    for tok in tokens:
        if tok in stop:
            continue
        if tok not in out:
            out.append(tok)
        if len(out) >= 4:
            break
    return " ".join(out)


def _is_fast_tag_query(q: str) -> bool:
    return (q or "") in {"sleep", "work", "exercise", "social", "stress"}


def _build_route_messages(user_text: str) -> List[Dict[str, str]]:
    schema = {
        "intent": "diary_qa|general",
        "query": "",
        "top_k": 5,
        "recent_n": 8,
        "char_budget": 3000,
        "lang": "zh",
    }

    system = (
        "You are a routing engine for a diary assistant.\n"
        "Return ONE valid JSON object ONLY. No markdown. No extra text.\n"
        "Keys MUST match schema exactly.\n"
        "intent: 'diary_qa' for questions about user's diary/history; 'general' for general knowledge.\n"
        "query: short retrieval query (<= 6 words). Empty for general.\n"
        "top_k: 0-8, recent_n: 0-12, char_budget: 1200-6000\n"
        "lang: 'zh' if user message mainly Chinese else 'en'\n"
        f"prompt_version={ROUTE_PROMPT_VERSION}"
    )
    user = json.dumps({"schema": schema, "user_text": user_text}, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_qwen_messages(*, user_text: str, context_pack_json: str, lang: str, intent: str) -> List[Dict[str, str]]:
    if lang == "zh":
        system = (
            "你是一个检索驱动的日记助理。\n"
            "必须输出一个 JSON 对象，且只能输出 JSON（无多余文本）。\n"
            "Schema: {answer: string, status: 'ok'|'not_recorded', evidence: {entry_ids: number[], card_ids: string[]}}\n"
            "硬规则：\n"
            "1) 若 intent=diary_qa：所有关于用户日记/历史的事实只能来自 CONTEXT_PACK_JSON。\n"
            "2) 若 CONTEXT_PACK_JSON 中没有足够证据支撑用户问题（diary_qa），必须输出 status='not_recorded'，并且 answer 必须精确为：未记录。\n"
            "3) 若 intent=general：可以回答常识，但不得声称来自日记；仍按 schema 输出。\n"
            f"prompt_version={ANSWER_PROMPT_VERSION}"
        )
    else:
        system = (
            "You are a retrieval-grounded diary assistant.\n"
            "You MUST output one JSON object only (no extra text).\n"
            "Schema: {answer: string, status: 'ok'|'not_recorded', evidence: {entry_ids: number[], card_ids: string[]}}\n"
            "Hard rules:\n"
            "1) If intent=diary_qa: any diary/history facts MUST come only from CONTEXT_PACK_JSON.\n"
            "2) If CONTEXT_PACK_JSON lacks sufficient evidence for diary_qa, output status='not_recorded' and answer MUST be exactly: Not recorded.\n"
            "3) If intent=general: you may answer normally but never claim it came from the diary.\n"
            f"prompt_version={ANSWER_PROMPT_VERSION}"
        )

    user = (
        f"intent={intent}\n"
        "QUESTION:\n" + (user_text or "") + "\n\n"
        "CONTEXT_PACK_JSON:\n" + (context_pack_json or "{}")
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class CascadeBot:
    def __init__(
        self,
        *,
        client: Optional[OllamaClient] = None,
        phi_model: str = DEFAULT_PHI_MODEL,
        qwen_model: str = DEFAULT_QWEN_MODEL,
        default_top_k: int = 5,
        default_recent_n: int = 8,
        default_char_budget: int = 3000,
    ) -> None:
        self.client = client or OllamaClient(timeout_s=QWEN_TIMEOUT_S)
        self.phi_model = phi_model
        self.qwen_model = qwen_model
        self.default_top_k = int(default_top_k)
        self.default_recent_n = int(default_recent_n)
        self.default_char_budget = int(default_char_budget)

    async def chat(
        self,
        user_text: str,
        *,
        debug: bool = False,
        preferred_provider: Optional[str] = None,
        force_cloud: bool = False,
        force_local: bool = False,
        **_ignored: Any,
    ) -> Dict[str, Any]:
        lang = _detect_lang(user_text)
        t0 = time.perf_counter()
        deadline = t0 + TOTAL_TIMEOUT_S
        logger.info(f"cascade_chat:start lang={lang} total_timeout_s={TOTAL_TIMEOUT_S}")

        fast_q = _fallback_query(user_text)
        use_phi_route = not _is_fast_tag_query(fast_q)

        route: Dict[str, Any] = {
            "intent": "diary_qa",
            "query": fast_q if _is_fast_tag_query(fast_q) else "",
            "top_k": self.default_top_k,
            "recent_n": self.default_recent_n,
            "char_budget": self.default_char_budget,
            "lang": lang,
        }
        route_ms = 0
        route_err: Optional[str] = None

        if use_phi_route:
            try:
                remain = deadline - time.perf_counter()
                if remain <= 3:
                    raise asyncio.TimeoutError()

                phi_timeout = min(PHI_TIMEOUT_S, max(1.0, remain - 3.0))

                msgs = _build_route_messages(user_text)
                coro = self.client.chat_text(
                    model=self.phi_model,
                    messages=msgs,
                    options={"temperature": 0, "top_p": 0.1, "num_predict": PHI_NUM_PREDICT},
                )
                text, route_ms = await asyncio.wait_for(coro, timeout=phi_timeout)

                obj = json.loads(_extract_first_json_obj(text))
                if isinstance(obj, dict):
                    route["intent"] = str(obj.get("intent") or route["intent"]).strip() or route["intent"]
                    route["query"] = str(obj.get("query") or "").strip()
                    route["lang"] = str(obj.get("lang") or route["lang"]).strip() or route["lang"]
                    route["top_k"] = _clamp_int(obj.get("top_k"), 0, 8, int(route["top_k"]))
                    route["recent_n"] = _clamp_int(obj.get("recent_n"), 0, 12, int(route["recent_n"]))
                    route["char_budget"] = _clamp_int(obj.get("char_budget"), 1200, 6000, int(route["char_budget"]))
            except asyncio.TimeoutError:
                route_err = f"phi_route_timeout>{PHI_TIMEOUT_S}s"
            except Exception as e:
                route_err = f"phi_route_failed: {type(e).__name__}: {e}"
        else:
            route_err = "phi_route_skipped_fast_tag"

        intent = str(route.get("intent") or "diary_qa").strip()
        lang = str(route.get("lang") or lang).strip()

        if intent == "diary_qa" and not route.get("query"):
            route["query"] = _fallback_query(user_text)

        if intent == "general":
            route["query"] = ""
            route["top_k"] = 0
            route["recent_n"] = 0

        pack = build_context_pack(
            str(route.get("query") or ""),
            top_k=int(route.get("top_k") or 0),
            recent_n=int(route.get("recent_n") or 0),
            char_budget=int(route.get("char_budget") or self.default_char_budget),
        )
        pack_text = build_context_pack_text(pack)

        qwen_msgs = _build_qwen_messages(user_text=user_text, context_pack_json=pack_text, lang=lang, intent=intent)

        ans_text = ""
        ans_ms = 0
        qwen_err: Optional[str] = None

        async def _local_chat(*, messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int, **_kw: Any) -> ProviderResult:
            text, ms = await self.client.chat_text(
                model=model,
                messages=messages,
                options={"temperature": float(temperature), "top_p": 0.1, "num_predict": int(max_tokens)},
            )
            return ProviderResult(
                content=text,
                raw={"content": text},
                provider="ollama",
                model=model,
                ms=int(ms),
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
            )

        try:
            remain2 = deadline - time.perf_counter()
            if remain2 <= 1:
                raise asyncio.TimeoutError()

            if routed_generate is None:
                # Router not available yet: keep legacy local behavior.
                ans_text, ans_ms = await self.client.chat_text(
                    model=self.qwen_model,
                    messages=qwen_msgs,
                    options={"temperature": 0, "top_p": 0.1, "num_predict": QWEN_NUM_PREDICT},
                )
            else:
                gen_payload = {
                    "intent": intent,
                    "prompt_version": ANSWER_PROMPT_VERSION,
                    "local_model": self.qwen_model,
                    "is_idle": False,
                    "fallback_backend": "local",
                }
                if preferred_provider:
                    gen_payload["preferred_provider"] = str(preferred_provider).strip().lower()
                if force_cloud:
                    gen_payload["force_cloud"] = True
                if force_local:
                    gen_payload["force_local"] = True

                if inspect.iscoroutinefunction(routed_generate):
                    res = await asyncio.wait_for(
                        routed_generate(
                            task="chat_answer",
                            payload=gen_payload,
                            messages=qwen_msgs,
                            temperature=0.0,
                            max_tokens=QWEN_NUM_PREDICT,
                            local_chat=_local_chat,
                        ),
                        timeout=max(1.0, remain2),
                    )
                else:
                    res = await asyncio.wait_for(
                        asyncio.to_thread(
                            routed_generate,
                            task="chat_answer",
                            payload=gen_payload,
                            messages=qwen_msgs,
                            temperature=0.0,
                            max_tokens=QWEN_NUM_PREDICT,
                            local_chat=_local_chat,
                        ),
                        timeout=max(1.0, remain2),
                    )
                ans_text, ans_ms = (res.content or ""), int(res.ms or 0)
        except asyncio.TimeoutError:
            qwen_err = f"answer_timeout>{TOTAL_TIMEOUT_S}s"
            ans_text, ans_ms = "", 0
        except ProviderError as e:
            qwen_err = f"answer_provider_error: {e}"
            ans_text, ans_ms = "", 0
        except Exception as e:
            qwen_err = f"answer_failed: {type(e).__name__}: {e}"
            ans_text, ans_ms = "", 0

        qwen_obj: Dict[str, Any] = {}
        parse_err: Optional[str] = None
        try:
            qwen_obj = json.loads(_extract_first_json_obj(ans_text))
            if not isinstance(qwen_obj, dict):
                qwen_obj = {}
        except Exception as e:
            parse_err = f"qwen_json_parse_failed: {e}"
            qwen_obj = {}

        status = str(qwen_obj.get("status") or "").strip()
        answer = str(qwen_obj.get("answer") or "").strip()
        evidence = qwen_obj.get("evidence") if isinstance(qwen_obj.get("evidence"), dict) else {}

        not_recorded_text = "未记录" if lang == "zh" else "Not recorded"

        if intent == "diary_qa" and qwen_err:
            out: Dict[str, Any] = {"reply": not_recorded_text}
            if debug:
                out["debug"] = {
                    "route": route,
                    "route_ms": int(route_ms),
                    "route_err": route_err,
                    "context_pack_meta": pack.get("meta"),
                    "context_pack_len": len(pack_text),
                    "models": {"phi": self.phi_model, "qwen": self.qwen_model},
                    "answer_ms": int(ans_ms),
                    "qwen_err": qwen_err,
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                    "total_timeout_s": TOTAL_TIMEOUT_S,
                    "remaining_s": max(0.0, float(deadline - time.perf_counter())),
                }
            return out

        if intent == "diary_qa":
            if status == "not_recorded":
                answer = not_recorded_text
            if not answer:
                answer = not_recorded_text
                status = "not_recorded"
            if answer == not_recorded_text and status != "not_recorded":
                status = "not_recorded"
        else:
            if not answer and parse_err:
                answer = (ans_text or "").strip() or not_recorded_text
                status = status or "ok"

        out: Dict[str, Any] = {"reply": answer}
        if debug:
            out["debug"] = {
                "route": route,
                "route_ms": int(route_ms),
                "route_err": route_err,
                "context_pack_meta": pack.get("meta"),
                "context_pack_len": len(pack_text),
                "models": {"phi": self.phi_model, "qwen": self.qwen_model},
                "answer_ms": int(ans_ms),
                "qwen_err": qwen_err,
                "qwen_status": status,
                "qwen_parse_err": parse_err,
                "qwen_evidence": evidence,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "total_timeout_s": TOTAL_TIMEOUT_S,
                "remaining_s": max(0.0, float(deadline - time.perf_counter())),
            }
        logger.info(f"cascade_chat:done status={status} elapsed_ms={int((time.perf_counter() - t0) * 1000)}")
        return out
