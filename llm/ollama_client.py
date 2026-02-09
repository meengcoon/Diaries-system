from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

_RETRY_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}


class OllamaError(RuntimeError):
    pass


def _snip(text: str | None, n: int = 800) -> str:
    if not text:
        return ""
    s = text.replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())
    if len(s) <= n:
        return s
    return s[:n] + "…"


class OllamaClient:
    """Minimal Ollama HTTP client without third-party runtime dependency."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_s: float = 0.0,
        *,
        max_retries: int | None = None,
        keep_alive: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout_s = float(timeout_s)
        self.connect_timeout_s = float(os.getenv("OLLAMA_CONNECT_TIMEOUT_S", "10"))
        self.read_timeout_s = None if self.timeout_s <= 0 else self.timeout_s
        self.max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", "2")) if max_retries is None else int(max_retries)
        self.retry_backoff_s = float(os.getenv("OLLAMA_RETRY_BACKOFF_S", "0.6"))
        self.default_keep_alive = keep_alive or os.getenv("OLLAMA_KEEP_ALIVE", "30m")

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def aclose(self) -> None:
        return None

    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        parts: List[str] = []
        for m in messages:
            role = (m.get("role") or "user").strip().lower()
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"User: {content}")
        parts.append("Assistant:")
        return "\n".join(parts) + "\n"

    async def _sleep_backoff(self, attempt: int) -> None:
        delay = self.retry_backoff_s * (2 ** attempt)
        if delay > 8.0:
            delay = 8.0
        await asyncio.sleep(delay)

    def _http_timeout(self) -> float:
        # urllib has a single timeout; use a conservative merged timeout.
        if self.read_timeout_s is None:
            return max(self.connect_timeout_s, 300.0)
        return max(self.connect_timeout_s, float(self.read_timeout_s))

    def _post_json_sync(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._http_timeout()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}

    async def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._post_json_sync, url, payload)

    async def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
        keep_alive: str | None = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        msg_count = len(messages or [])
        msg_chars = sum(len(str((m or {}).get("content") or "")) for m in (messages or []))

        chat_payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options or {},
            "keep_alive": keep_alive or self.default_keep_alive,
        }

        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                data = await self._post_json(f"{self.base_url}/api/chat", chat_payload)
                data["_ms"] = int((time.perf_counter() - t0) * 1000)
                return data

            except urllib.error.HTTPError as e:
                status = int(getattr(e, "code", 0) or 0)
                body = e.read().decode("utf-8", errors="replace")

                if status == 404:
                    prompt = self._messages_to_prompt(messages)
                    gen_payload = {
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": options or {},
                        "keep_alive": keep_alive or self.default_keep_alive,
                    }
                    try:
                        gen = await self._post_json(f"{self.base_url}/api/generate", gen_payload)
                        data = {
                            "model": model,
                            "message": {"role": "assistant", "content": gen.get("response", "")},
                            "done": gen.get("done", True),
                        }
                        data["_ms"] = int((time.perf_counter() - t0) * 1000)
                        return data
                    except Exception as ge:
                        last_exc = ge
                        if attempt < self.max_retries:
                            await self._sleep_backoff(attempt)
                            continue
                        raise OllamaError(
                            f"ollama generate failed after chat 404 attempt={attempt+1}/{self.max_retries+1} "
                            f"model={model} msgs={msg_count} chars={msg_chars} err={type(ge).__name__}: {ge}"
                        ) from ge

                retryable = status in _RETRY_HTTP_STATUS
                last_exc = e
                if retryable and attempt < self.max_retries:
                    await self._sleep_backoff(attempt)
                    continue
                raise OllamaError(
                    f"ollama chat failed attempt={attempt+1}/{self.max_retries+1} model={model} "
                    f"msgs={msg_count} chars={msg_chars} status={status} body={_snip(body)}"
                ) from e

            except Exception as e:
                last_exc = e
                if attempt < self.max_retries:
                    await self._sleep_backoff(attempt)
                    continue
                raise OllamaError(
                    f"ollama chat failed attempt={attempt+1}/{self.max_retries+1} model={model} "
                    f"msgs={msg_count} chars={msg_chars} err={type(e).__name__}: {e!r}"
                ) from e

        raise OllamaError(
            f"ollama chat failed: model={model} err={type(last_exc).__name__ if last_exc else 'Unknown'}"
        )

    async def chat_text(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, int]:
        data = await self.chat(model=model, messages=messages, options=options)
        msg = data.get("message") or {}
        content = msg.get("content") or ""
        return str(content), int(data.get("_ms", 0))
