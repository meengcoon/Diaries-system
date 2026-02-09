from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .base import BaseProvider, ProviderError, ProviderResult


def _is_retryable_status(status: int) -> bool:
    return status == 408 or status == 429 or 500 <= status <= 599


class DeepSeekProvider(BaseProvider):
    """DeepSeek OpenAI-compatible Chat Completions provider."""

    name = "deepseek"

    def __init__(self, *, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _post_json(self, url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout_connect_s: float = 10.0,
        timeout_read_s: float = 60.0,
        retries: int = 2,
        response_format: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        t0 = time.perf_counter()
        last_err: Optional[ProviderError] = None
        timeout_s = max(float(timeout_connect_s), float(timeout_read_s))

        for attempt in range(retries + 1):
            try:
                raw = self._post_json(url, headers, payload, timeout_s)
                content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = raw.get("usage") or {}
                ms = int((time.perf_counter() - t0) * 1000)
                return ProviderResult(
                    content=content,
                    raw=raw,
                    provider=self.name,
                    model=model,
                    ms=ms,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                )
            except urllib.error.HTTPError as e:
                status = int(getattr(e, "code", 0) or 0)
                body = e.read().decode("utf-8", errors="replace")
                retryable = _is_retryable_status(status)
                last_err = ProviderError(
                    code="http_status_error",
                    status=status,
                    retryable=retryable,
                    detail=body[:600] or str(e),
                )
            except Exception as e:
                last_err = ProviderError(
                    code=type(e).__name__,
                    status=None,
                    retryable=True,
                    detail=str(e),
                )

            if last_err.retryable and attempt < retries:
                time.sleep(0.6 * (2 ** attempt))
                continue
            raise last_err

        raise ProviderError(code="unknown", status=None, retryable=False, detail="Unexpected provider loop exit")
