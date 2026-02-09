from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    text: str
    mode: Literal["chat"] = "chat"
    debug: bool = False
    preferred_provider: Optional[Literal["deepseek", "qwen"]] = None
    force_cloud: bool = False
    force_local: bool = False


class ChatResponse(BaseModel):
    reply: str
    mode: str
    debug: Optional[dict] = None


def _env_bool(name: str, default: bool) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    """M4: cascade chat (Phi route + context_pack + Qwen grounded answer).

    Hard requirements:
    - Never hang the HTTP response (bounded latency)
    - Fail-closed on errors/timeouts (=> "未记录")
    """
    bot = getattr(request.app.state, "bot", None)
    logger.info(f"聊天请求: mode={req.mode}, text长度={len(req.text)}, debug={req.debug}")

    if bot is None:
        dbg = {"server_err": "bot_not_initialized"} if req.debug else None
        return ChatResponse(reply="未记录", mode=req.mode, debug=dbg)

    chat_timeout_s = float(os.getenv("CHAT_TIMEOUT_S", "70"))
    default_force_cloud = _env_bool("CHAT_FORCE_CLOUD", False)
    default_provider = (os.getenv("CHAT_PREFERRED_PROVIDER") or os.getenv("CLOUD_DEFAULT_PROVIDER") or "").strip().lower()
    preferred_provider = req.preferred_provider or (default_provider if default_provider in {"deepseek", "qwen"} else None)
    force_cloud = bool(req.force_cloud or (default_force_cloud and not req.force_local))

    try:
        # Support both legacy sync bot and async cascade bot.
        try:
            out = bot.chat(
                req.text,
                debug=req.debug,
                preferred_provider=preferred_provider,
                force_cloud=force_cloud,
                force_local=req.force_local,
            )  # type: ignore[attr-defined]
        except TypeError:
            out = bot.chat(req.text)  # type: ignore[attr-defined]

        if asyncio.iscoroutine(out):
            out = await asyncio.wait_for(out, timeout=chat_timeout_s)

        if isinstance(out, dict):
            reply = str(out.get("reply", ""))
            dbg = out.get("debug") if req.debug else None
        else:
            reply = str(out)
            dbg = None

        return ChatResponse(reply=reply, mode=req.mode, debug=dbg)

    except asyncio.TimeoutError:
        logger.warning(f"/api/chat timeout after {chat_timeout_s}s")
        dbg = {"server_err": "chat_timeout", "timeout_s": chat_timeout_s} if req.debug else None
        return ChatResponse(reply="未记录", mode=req.mode, debug=dbg)

    except Exception as e:
        logger.exception(f"/api/chat failed: {type(e).__name__}: {e}")
        dbg = {"server_err": f"chat_failed: {type(e).__name__}: {e}"} if req.debug else None
        return ChatResponse(reply="未记录", mode=req.mode, debug=dbg)
