from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from core.settings import env_bool, env_float, env_int, env_str
from pipeline.chat_memory import update_chat_memory
from pipeline.local_stt import transcribe_audio_file_local
from storage.repo_chat import (
    create_chat_session,
    get_chat_session,
    insert_chat_message,
    list_chat_messages,
    list_chat_sessions,
    update_chat_session,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_MODEL_UNAVAILABLE_REPLY = "模型暂时不可用，请稍后重试"
MAX_VOICE_CHAT_UPLOAD_BYTES = env_int("DIARY_MAX_AUDIO_UPLOAD_MB", 25) * 1024 * 1024


class ChatRequest(BaseModel):
    text: str
    mode: Literal["chat"] = "chat"
    session_id: Optional[int] = None
    debug: bool = False
    preferred_provider: Optional[Literal["deepseek", "qwen"]] = None
    force_cloud: bool = False
    force_local: bool = False


class ChatResponse(BaseModel):
    reply: str
    mode: str
    session_id: Optional[int] = None
    debug: Optional[dict] = None


class VoiceChatResponse(BaseModel):
    transcript: str
    reply: str
    mode: str = "chat"
    session_id: Optional[int] = None
    audio_base64: Optional[str] = None
    audio_mime: Optional[str] = None
    tts_ok: bool = False
    warning: Optional[str] = None
    debug: Optional[dict] = None


class ChatSessionSummary(BaseModel):
    id: int
    created_at: str
    updated_at: str
    title: str
    summary: Optional[str] = None
    pinned: int = 0
    last_user_text: Optional[str] = None
    message_count: int = 0


class ChatSessionListResponse(BaseModel):
    items: List[ChatSessionSummary]


class ChatSessionMessage(BaseModel):
    id: int
    session_id: Optional[int] = None
    created_at: str
    role: str
    mode: str
    text: str
    meta_json: Optional[dict] = None


class ChatSessionDetailResponse(BaseModel):
    session: Optional[ChatSessionSummary] = None
    items: List[ChatSessionMessage]

def _derive_session_title(text: str) -> str:
    raw = " ".join(str(text or "").strip().split())
    if not raw:
        return "新对话"
    raw = raw.replace("\n", " ")
    return raw[:24] + ("…" if len(raw) > 24 else "")


def _ensure_session(session_id: Optional[int], first_user_text: str) -> int:
    if session_id:
        existing = get_chat_session(int(session_id))
        if existing:
            return int(session_id)
    title = _derive_session_title(first_user_text)
    return create_chat_session(title=title, summary="聊天会话")


def _chat_with_bot(
    *,
    bot: Any,
    text: str,
    debug: bool,
    preferred_provider: Optional[str],
    force_cloud: bool,
    force_local: bool,
):
    return bot.chat(
        text,
        debug=debug,
        preferred_provider=preferred_provider,
        force_cloud=force_cloud,
        force_local=force_local,
    )  # type: ignore[attr-defined]


async def _run_chat_pipeline(
    *,
    bot: Any,
    text: str,
    mode: str,
    debug: bool,
    preferred_provider: Optional[str],
    force_cloud: bool,
    force_local: bool,
) -> ChatResponse:
    chat_timeout_s = env_float("CHAT_TIMEOUT_S", 70.0)
    default_force_cloud = env_bool("CHAT_FORCE_CLOUD", False)
    default_provider = (
        env_str("CHAT_PREFERRED_PROVIDER") or env_str("CLOUD_DEFAULT_PROVIDER") or ""
    ).strip().lower()
    preferred_provider = preferred_provider or (
        default_provider if default_provider in {"deepseek", "qwen"} else None
    )
    force_cloud = bool(force_cloud or (default_force_cloud and not force_local))

    try:
        try:
            out = _chat_with_bot(
                bot=bot,
                text=text,
                debug=debug,
                preferred_provider=preferred_provider,
                force_cloud=force_cloud,
                force_local=force_local,
            )
        except TypeError:
            out = bot.chat(text)  # type: ignore[attr-defined]

        if asyncio.iscoroutine(out):
            out = await asyncio.wait_for(out, timeout=chat_timeout_s)

        if isinstance(out, dict):
            reply = str(out.get("reply", ""))
            dbg = out.get("debug") if debug else None
        else:
            reply = str(out)
            dbg = None
        return ChatResponse(reply=reply, mode=mode, debug=dbg)
    except asyncio.TimeoutError:
        logger.warning(f"/api/chat timeout after {chat_timeout_s}s")
        dbg = {"server_err": "chat_timeout", "timeout_s": chat_timeout_s} if debug else None
        return ChatResponse(reply=_MODEL_UNAVAILABLE_REPLY, mode=mode, debug=dbg)
    except Exception as e:
        logger.exception(f"/api/chat failed: {type(e).__name__}: {e}")
        dbg = {"server_err": f"chat_failed: {type(e).__name__}: {e}"} if debug else None
        return ChatResponse(reply=_MODEL_UNAVAILABLE_REPLY, mode=mode, debug=dbg)


def _transcribe_local_bytes(audio_bytes: bytes, filename: str) -> str:
    suffix = Path(filename or "voice.webm").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(prefix="voice_chat_", suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()
        return transcribe_audio_file_local(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


async def _read_upload_limited(audio: UploadFile, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > int(max_bytes):
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "AUDIO_TOO_LARGE",
                        "message": f"audio file too large (> {int(max_bytes) // (1024 * 1024)}MB)",
                    },
                )
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        await audio.close()


@router.get("/api/chat/sessions", response_model=ChatSessionListResponse)
async def chat_sessions(limit: int = 60):
    items = list_chat_sessions(limit=max(1, min(int(limit or 60), 200)))
    return ChatSessionListResponse(items=items)


@router.post("/api/chat/session/new", response_model=ChatSessionSummary)
async def chat_session_new():
    session_id = create_chat_session(title="新对话", summary="聊天会话")
    row = get_chat_session(session_id)
    if not row:
        raise HTTPException(status_code=500, detail={"message": "会话创建失败"})
    return ChatSessionSummary(**row, last_user_text=None, message_count=0)


@router.get("/api/chat/session", response_model=ChatSessionDetailResponse)
async def chat_session_detail(id: int, limit: int = 200):
    session = get_chat_session(int(id))
    if not session:
        raise HTTPException(status_code=404, detail={"message": "会话不存在"})
    items = list_chat_messages(int(id), limit=max(1, min(int(limit or 200), 500)))
    return ChatSessionDetailResponse(session=session, items=items)


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    bot = getattr(request.app.state, "bot", None)
    logger.info(f"聊天请求: mode={req.mode}, text长度={len(req.text)}, debug={req.debug}")

    if bot is None:
        dbg = {"server_err": "bot_not_initialized"} if req.debug else None
        return ChatResponse(reply=_MODEL_UNAVAILABLE_REPLY, mode=req.mode, session_id=req.session_id, debug=dbg)

    session_id = _ensure_session(req.session_id, req.text)

    out = await _run_chat_pipeline(
        bot=bot,
        text=req.text,
        mode=req.mode,
        debug=req.debug,
        preferred_provider=req.preferred_provider,
        force_cloud=req.force_cloud,
        force_local=req.force_local,
    )
    out.session_id = session_id
    try:
        existing_session = get_chat_session(session_id)
        user_id = insert_chat_message(
            session_id=session_id,
            role="user",
            mode=req.mode,
            text=req.text,
            meta_json={"source": "api_chat"},
        )
        update_chat_memory(message_id=user_id, user_text=req.text, created_at=None)
        insert_chat_message(
            session_id=session_id,
            role="assistant",
            mode=req.mode,
            text=out.reply,
            meta_json={"source": "api_chat", "has_debug": bool(req.debug)},
        )
        if existing_session and str(existing_session.get("title") or "").strip() in {"", "新对话", "历史对话"}:
            update_chat_session(session_id, title=_derive_session_title(req.text), updated_at=None)
        else:
            update_chat_session(session_id, updated_at=None)
    except Exception as e:
        logger.exception(f"/api/chat persist failed: {type(e).__name__}: {e}")
    return out


@router.post("/api/voice/chat", response_model=VoiceChatResponse)
async def voice_chat(
    request: Request,
    audio: UploadFile = File(...),
    session_id: Optional[int] = Form(None),
    debug: bool = Form(False),
    mimic_voice: bool = Form(True),
    preferred_provider: Optional[str] = Form(None),
    force_cloud: bool = Form(False),
    force_local: bool = Form(False),
):
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail={"message": "bot not initialized"})

    raw = await _read_upload_limited(audio, max_bytes=MAX_VOICE_CHAT_UPLOAD_BYTES)
    if not raw:
        raise HTTPException(status_code=400, detail={"message": "空音频"})

    try:
        transcript = await asyncio.to_thread(
            _transcribe_local_bytes,
            raw,
            audio.filename or "voice.webm",
        )
    except Exception as e:
        logger.exception(f"/api/voice/chat stt failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail={"message": f"语音转写失败: {type(e).__name__}"})

    session_id = _ensure_session(session_id, transcript)
    chat_out = await _run_chat_pipeline(
        bot=bot,
        text=transcript,
        mode="chat",
        debug=debug,
        preferred_provider=preferred_provider if preferred_provider in {"deepseek", "qwen"} else None,
        force_cloud=force_cloud,
        force_local=force_local,
    )
    reply = chat_out.reply or _MODEL_UNAVAILABLE_REPLY

    try:
        existing_session = get_chat_session(session_id)
        user_id = insert_chat_message(
            session_id=session_id,
            role="user",
            mode="voice_chat",
            text=transcript,
            meta_json={"source": "voice_chat", "filename": audio.filename or "voice.webm"},
        )
        update_chat_memory(message_id=user_id, user_text=transcript)
        insert_chat_message(
            session_id=session_id,
            role="assistant",
            mode="voice_chat",
            text=reply,
            meta_json={"source": "voice_chat"},
        )
        if existing_session and str(existing_session.get("title") or "").strip() in {"", "新对话", "历史对话"}:
            update_chat_session(session_id, title=_derive_session_title(transcript))
        else:
            update_chat_session(session_id)
    except Exception as e:
        logger.exception(f"/api/voice/chat persist failed: {type(e).__name__}: {e}")

    warning = "语音合成功能已移除，仅返回文字回复。" if mimic_voice else None
    return VoiceChatResponse(
        transcript=transcript,
        reply=reply,
        mode="chat",
        session_id=session_id,
        audio_base64=None,
        audio_mime=None,
        tts_ok=False,
        warning=warning,
        debug=chat_out.debug if debug else None,
    )
