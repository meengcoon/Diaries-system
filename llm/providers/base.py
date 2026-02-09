# llm/providers/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class ProviderError(Exception):
    """Provider call error with retry classification."""

    code: str
    status: Optional[int]
    retryable: bool
    detail: str

    def __str__(self) -> str:  # pragma: no cover
        s = f"{self.code}"
        if self.status is not None:
            s += f" (HTTP {self.status})"
        if self.retryable:
            s += " [retryable]"
        return f"{s}: {self.detail}"


@dataclass(frozen=True)
class ProviderResult:
    """Normalized provider result across cloud/local backends."""

    content: str
    raw: Dict[str, Any]
    provider: str
    model: str
    ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class BaseProvider(Protocol):
    """Unified interface for LLM backends (DeepSeek/Qwen/etc.)."""

    name: str

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
        """Send chat-completions style request.

        Implementations should:
        - raise ProviderError on failure (retryable classified)
        - return ProviderResult with `content` and full `raw` response
        """
        ...


# Backwards-compat aliases (temporary). Remove once all call sites migrate.
LLMResult = ProviderResult
LLMProvider = BaseProvider