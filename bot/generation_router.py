import os
import re
import time
import asyncio
import inspect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from llm.providers import ProviderError, ProviderResult, get_provider
from llm.request_store import hash_request, store_meta, store_request, store_response
from storage.repo_llm_cache import get_cached_response_json, is_cache_enabled, upsert_cached_response_json
from storage.repo_llm_calls import insert_call, list_calls
from utils.redact import redact_messages


# Backward compatible intent set (your previous draft)
CLOUD_INTENTS = {"weekly_review", "persona_summary", "long_write"}
_PRIVACY_RANK = {"L0": 0, "L1": 1, "L2": 2}
_PII_PATTERNS = [
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"(?i)\bhttps?://[^\s]+"),
    re.compile(r"(?x)(?<!\w)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?!\w)"),
]


def _env_bool(name: str, default: bool) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    v = (os.getenv(name) or "").strip()
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = (os.getenv(name) or "").strip()
    if not v:
        return default
    try:
        return float(v)
    except Exception:
        return default


def _norm_privacy_level(level: Any) -> str:
    v = str(level or "").strip().upper()
    if v in _PRIVACY_RANK:
        return v
    return "L1"


def _infer_privacy_level(payload: Dict[str, Any]) -> str:
    if payload.get("raw_text") or payload.get("text"):
        return "L0"
    return "L1"


def _privacy_allowed(payload: Dict[str, Any]) -> tuple[bool, str]:
    max_level = _norm_privacy_level(os.getenv("CLOUD_MAX_PRIVACY_LEVEL", "L1"))
    req_level = _norm_privacy_level(payload.get("privacy_level") or _infer_privacy_level(payload))
    if _PRIVACY_RANK[req_level] > _PRIVACY_RANK[max_level]:
        return False, f"privacy_blocked req={req_level} max={max_level}"
    return True, req_level


def _sanitize_cloud_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = redact_messages(messages)
    clean: List[Dict[str, Any]] = []
    for m in out:
        m2 = dict(m)
        content = m2.get("content")
        if isinstance(content, str):
            s = content
            for pat in _PII_PATTERNS:
                s = pat.sub("__", s)
            m2["content"] = s
        clean.append(m2)
    return clean


def _filter_cloud_payload(payload: Dict[str, Any], *, allow_style_profile: bool) -> Dict[str, Any]:
    keep = {
        "intent",
        "prompt_version",
        "is_idle",
        "privacy_level",
        "use_for_training",
        "preferred_provider",
        "force_cloud",
        "force_local",
        "fallback_backend",
        "cloud_model",
        "local_model",
    }
    out = {k: payload[k] for k in keep if k in payload}
    if allow_style_profile and "style_profile" in payload:
        out["style_profile"] = payload["style_profile"]
    return out


def should_use_cloud(intent: str, *, force_cloud: bool = False) -> bool:
    """Legacy helper kept for compatibility."""
    if force_cloud:
        return True
    return (intent or "") in CLOUD_INTENTS


@dataclass(frozen=True)
class RouteDecision:
    backend: str  # "local" | "cloud"
    provider: Optional[str]
    model: str
    prompt_version: str
    reason: str
    fallback_backend: str = "local"  # "local" | "cloud" | "none"


def _estimate_chars_from_messages(messages: List[Dict[str, str]]) -> int:
    n = 0
    for m in messages:
        n += len((m.get("role") or ""))
        n += len((m.get("content") or ""))
    return n


def _cloud_circuit_open(provider: str) -> bool:
    """Simple circuit breaker based on recent failed calls (DB audit).

    Env:
      - CLOUD_FAIL_WINDOW_S (default 600)
      - CLOUD_FAIL_THRESHOLD (default 3)

    If failures >= threshold within window => circuit open => route to local.
    """
    window_s = _env_int("CLOUD_FAIL_WINDOW_S", 600)
    threshold = _env_int("CLOUD_FAIL_THRESHOLD", 3)
    if threshold <= 0:
        return False

    now = datetime.now(timezone.utc)
    tmin = (now - timedelta(seconds=window_s)).isoformat(timespec="seconds")

    try:
        rows = list_calls(provider=provider, status="failed", time_min=tmin, limit=threshold)
        return len(rows) >= threshold
    except Exception:
        # If audit table isn't available for some reason, do not hard-fail routing.
        return False


def route(task: str, payload: Dict[str, Any]) -> RouteDecision:
    """Decide local vs cloud.

    Inputs (payload keys used if present):
      - intent: optional string
      - force_cloud: bool
      - force_local: bool
      - preferred_provider: "deepseek"|"qwen"
      - is_idle: bool
      - messages: list[dict] (optional; if absent, we fall back to text)
      - text/raw_text/user_text: string (optional)
      - prompt_version: string (required by audit; default "v1")

    Env switches:
      - CLOUD_ENABLED (default 0)
      - CLOUD_ONLY_WHEN_IDLE (default 0)
      - CLOUD_CHAR_THRESHOLD (default 6000)
      - CLOUD_DEFAULT_PROVIDER (default "deepseek")
      - DEEPSEEK_MODEL / QWEN_MODEL (defaults: "deepseek-chat" / "qwen-plus")
    """

    task = (task or "").strip().lower()
    intent = (payload.get("intent") or task or "").strip()
    prompt_version = str(payload.get("prompt_version") or "v1")

    # Hard overrides
    if bool(payload.get("force_local")):
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason="force_local",
            fallback_backend="none",
        )

    cloud_enabled = _env_bool("CLOUD_ENABLED", False)
    allow_cloud_inference = _env_bool("ALLOW_CLOUD_INFERENCE", True)
    allow_cloud_training = _env_bool("ALLOW_CLOUD_TRAINING", False)
    block_raw_text_upload = _env_bool("BLOCK_RAW_TEXT_UPLOAD", True)
    only_when_idle = _env_bool("CLOUD_ONLY_WHEN_IDLE", False)
    is_idle = bool(payload.get("is_idle", True))
    use_for_training = bool(payload.get("use_for_training", False))

    # Default: block_analyze/mem_update stay local (Phi/Qwen local) unless force_cloud.
    if not bool(payload.get("force_cloud")) and task in {"block_analyze", "mem_update"}:
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason=f"task={task} default_local",
            fallback_backend="none",
        )

    if not cloud_enabled and not bool(payload.get("force_cloud")):
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason="cloud_disabled",
            fallback_backend="none",
        )

    if use_for_training and not allow_cloud_training:
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason="cloud_training_disabled",
            fallback_backend="none",
        )

    if (not use_for_training) and not allow_cloud_inference:
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason="cloud_inference_disabled",
            fallback_backend="none",
        )

    if block_raw_text_upload and (payload.get("raw_text") is not None):
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason="raw_text_upload_blocked",
            fallback_backend="none",
        )

    allowed, privacy_reason = _privacy_allowed(payload)
    if not allowed:
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason=privacy_reason,
            fallback_backend="none",
        )

    if only_when_idle and not is_idle and not bool(payload.get("force_cloud")):
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason="cloud_only_when_idle",
            fallback_backend="none",
        )

    # Decide by intent + length threshold
    messages = payload.get("messages")
    if isinstance(messages, list):
        char_len = _estimate_chars_from_messages(messages)  # best effort
    else:
        text = payload.get("text") or payload.get("raw_text") or payload.get("user_text") or ""
        char_len = len(str(text))

    char_threshold = _env_int("CLOUD_CHAR_THRESHOLD", 6000)

    want_cloud = bool(payload.get("force_cloud")) or should_use_cloud(intent) or (char_len >= char_threshold)

    if not want_cloud:
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason=f"below_threshold len={char_len}",
            fallback_backend="none",
        )

    provider = (payload.get("preferred_provider") or os.getenv("CLOUD_DEFAULT_PROVIDER") or "deepseek").strip().lower()
    if provider not in {"deepseek", "qwen"}:
        provider = "deepseek"

    if _cloud_circuit_open(provider) and not bool(payload.get("force_cloud")):
        return RouteDecision(
            backend="local",
            provider=None,
            model=str(payload.get("local_model") or ""),
            prompt_version=prompt_version,
            reason=f"circuit_open provider={provider}",
            fallback_backend="none",
        )

    # Select cloud model
    if provider == "qwen":
        model = str(
            payload.get("cloud_model")
            or os.getenv("QWEN_CLOUD_MODEL")
            or os.getenv("QWEN_MODEL")
            or "qwen-plus"
        )
    else:
        model = str(payload.get("cloud_model") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat")

    return RouteDecision(
        backend="cloud",
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        reason=f"cloud len={char_len} intent={intent}",
        fallback_backend=str(payload.get("fallback_backend") or "local"),
    )


def _provider_result_from_cached_raw(*, provider: str, model: str, raw: Dict[str, Any]) -> ProviderResult:
    content = (
        raw.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    usage = raw.get("usage") or {}
    return ProviderResult(
        content=content,
        raw=raw,
        provider=provider,
        model=model,
        ms=0,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )


LocalChatFn = Callable[..., ProviderResult]


def _run_local_chat(local_chat: LocalChatFn, **kwargs: Any) -> ProviderResult:
    """Run local_chat that may be sync or async.

    generation_router.generate() is synchronous. When local_chat is async, execute it
    in this context via asyncio.run (safe when called from worker/thread paths).
    """
    res = local_chat(**kwargs)
    if inspect.isawaitable(res):
        return asyncio.run(res)
    return res


def generate(
    *,
    task: str,
    payload: Dict[str, Any],
    messages: List[Dict[str, str]],
    response_format: Optional[Dict[str, Any]] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    local_chat: Optional[LocalChatFn] = None,
) -> ProviderResult:
    """Generate with routing, caching, request-store and DB audit.

    This is the single entry you should call from cascade_bot / jobs:
      - route(...) => decision
      - if cloud: cache -> provider.chat -> cache write
      - always: insert_call(...) audit row
      - failure: record failed audit row; optional fallback to local

    `local_chat` should accept (messages=..., model=..., temperature=..., max_tokens=..., **kwargs)
    and return ProviderResult.
    """

    decision = route(task, {**payload, "messages": messages})

    # Cloud redaction: only redact content when routing to cloud.
    # This ensures local processing remains untouched while cloud payloads are sanitized.
    if decision.backend == "cloud":
        allow_style_profile = _env_bool("ALLOW_STYLE_PROFILE_UPLOAD", True)
        payload = _filter_cloud_payload(payload, allow_style_profile=allow_style_profile)
        messages = _sanitize_cloud_messages(messages)

    # -------- Local path --------
    if decision.backend == "local":
        if not local_chat:
            raise RuntimeError(
                "Route decision is local but local_chat is not provided. "
                "Wire bot/cascade_bot.py to pass the Ollama local chat function."
            )
        t0 = time.perf_counter()
        res = _run_local_chat(
            local_chat,
            messages=messages,
            model=decision.model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        ms = int((time.perf_counter() - t0) * 1000)

        # Audit local call too (provider=ollama)
        try:
            req_hash = hash_request(
                provider="ollama",
                model=decision.model or "local",
                messages=messages,
                params={"temperature": temperature, "max_tokens": max_tokens, "task": task},
                prompt_version=decision.prompt_version,
            )
            store_request(req_hash, {"provider": "ollama", "model": decision.model, "messages": messages})
            store_response(req_hash, res.raw if isinstance(res.raw, dict) else {"content": res.content})
            insert_call(
                provider="ollama",
                model=decision.model or "local",
                prompt_version=decision.prompt_version,
                request_hash=req_hash,
                request_json={"messages": messages, "temperature": temperature, "max_tokens": max_tokens, "task": task},
                response_json=res.raw if isinstance(res.raw, dict) else {"content": res.content},
                status="ok",
                ms=ms,
                tokens_prompt=res.prompt_tokens,
                tokens_completion=res.completion_tokens,
                tokens_total=res.total_tokens,
            )
        except Exception:
            # Never block normal execution on audit failures.
            pass

        # Ensure ms is reasonable
        if res.ms <= 0:
            return ProviderResult(
                content=res.content,
                raw=res.raw,
                provider=res.provider,
                model=res.model,
                ms=ms,
                prompt_tokens=res.prompt_tokens,
                completion_tokens=res.completion_tokens,
                total_tokens=res.total_tokens,
            )
        return res

    # -------- Cloud path --------
    assert decision.provider is not None
    provider_name = decision.provider
    provider = get_provider(provider_name)

    timeout_connect_s = _env_float("CLOUD_TIMEOUT_CONNECT_S", 10.0)
    timeout_read_s = _env_float("CLOUD_TIMEOUT_READ_S", 120.0)
    retries = _env_int("CLOUD_RETRIES", 2)
    ttl_s = _env_int("LLM_CACHE_TTL_S", 0)
    ttl_arg = ttl_s if ttl_s > 0 else None

    req_params = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "task": task,
        "response_format": response_format,
    }

    req_hash = hash_request(
        provider=provider_name,
        model=decision.model,
        messages=messages,
        params=req_params,
        prompt_version=decision.prompt_version,
    )

    # Persist request payload (redacted by request_store)
    store_request(
        req_hash,
        {
            "provider": provider_name,
            "model": decision.model,
            "prompt_version": decision.prompt_version,
            "messages": messages,
            "params": req_params,
        },
    )

    cache_hit = False
    if is_cache_enabled():
        cached = get_cached_response_json(provider_name, decision.model, req_hash, ttl_s=ttl_arg)
        if cached:
            cache_hit = True
            res = _provider_result_from_cached_raw(provider=provider_name, model=decision.model, raw=cached)
            try:
                insert_call(
                    provider=provider_name,
                    model=decision.model,
                    prompt_version=decision.prompt_version,
                    request_hash=req_hash,
                    request_json={"messages": messages, "params": req_params, "task": task, "cache": True},
                    response_json=cached,
                    status="ok",
                    ms=0,
                    tokens_prompt=res.prompt_tokens,
                    tokens_completion=res.completion_tokens,
                    tokens_total=res.total_tokens,
                )
            except Exception:
                pass
            return res

    # Not cached: real call
    t0 = time.perf_counter()
    try:
        res = provider.chat(
            messages,
            decision.model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_connect_s=timeout_connect_s,
            timeout_read_s=timeout_read_s,
            retries=retries,
            response_format=response_format,
            meta={"task": task, "prompt_version": decision.prompt_version},
        )
        ms = int((time.perf_counter() - t0) * 1000)

        # Persist response + cache
        try:
            store_response(req_hash, res.raw)
            upsert_cached_response_json(provider_name, decision.model, req_hash, res.raw)
        except Exception:
            pass

        try:
            insert_call(
                provider=provider_name,
                model=decision.model,
                prompt_version=decision.prompt_version,
                request_hash=req_hash,
                request_json={"messages": messages, "params": req_params, "task": task, "cache_hit": cache_hit},
                response_json=res.raw,
                status="ok",
                ms=ms,
                tokens_prompt=res.prompt_tokens,
                tokens_completion=res.completion_tokens,
                tokens_total=res.total_tokens,
            )
        except Exception:
            pass

        # Prefer measured ms if provider returned 0
        if res.ms <= 0:
            return ProviderResult(
                content=res.content,
                raw=res.raw,
                provider=res.provider,
                model=res.model,
                ms=ms,
                prompt_tokens=res.prompt_tokens,
                completion_tokens=res.completion_tokens,
                total_tokens=res.total_tokens,
            )
        return res

    except ProviderError as e:
        ms = int((time.perf_counter() - t0) * 1000)
        try:
            store_meta(
                req_hash,
                {
                    "ok": False,
                    "error": str(e),
                    "provider": provider_name,
                    "model": decision.model,
                    "task": task,
                    "ms": ms,
                    "cache_hit": cache_hit,
                    "reason": decision.reason,
                },
            )
        except Exception:
            pass

        try:
            insert_call(
                provider=provider_name,
                model=decision.model,
                prompt_version=decision.prompt_version,
                request_hash=req_hash,
                request_json={"messages": messages, "params": req_params, "task": task},
                response_json=None,
                status="failed",
                error=str(e),
                ms=ms,
            )
        except Exception:
            pass

        # Optional fallback to local
        if decision.fallback_backend == "local" and local_chat is not None:
            t1 = time.perf_counter()
            local_res = _run_local_chat(
                local_chat,
                messages=messages,
                model=payload.get("local_model") or "",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            ms_local = int((time.perf_counter() - t1) * 1000)
            try:
                insert_call(
                    provider="ollama",
                    model=payload.get("local_model") or "local",
                    prompt_version=decision.prompt_version,
                    request_hash=req_hash,
                    request_json={"messages": messages, "params": req_params, "task": task, "fallback_from": provider_name},
                    response_json=local_res.raw if isinstance(local_res.raw, dict) else {"content": local_res.content},
                    status="ok",
                    ms=ms_local,
                )
            except Exception:
                pass
            return local_res

        raise


__all__ = [
    "RouteDecision",
    "route",
    "generate",
    "should_use_cloud",
    "CLOUD_INTENTS",
]
