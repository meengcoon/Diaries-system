from __future__ import annotations

import mimetypes
import re
import subprocess
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response

from storage.repo_audio import get_audio_entry
from utils.ffmpeg import find_ffmpeg
from .diary_file_service import diaries_dir


def build_transcript_profile(text: str) -> Dict[str, Any]:
    s = str(text or "").strip()
    if not s:
        return {
            "sample_chars": 0,
            "traits": ["暂无可用转写文本。"],
            "signals": {},
        }
    sentences = [x.strip() for x in re.split(r"[。！？!?]", s) if x.strip()]
    sent_count = max(1, len(sentences))
    avg_sent_len = round(sum(len(x) for x in sentences) / sent_count, 1)
    fillers = re.findall(r"(然后|就是|那个|嗯|呃|你知道吧)", s)
    self_repair = re.findall(r"(不对|我的意思是|我是说|更准确地说)", s)
    timeline = re.findall(r"(\d+点半|\d+点|\d+分钟|早上|中午|下午|晚上|今天|昨天)", s)
    emotion = re.findall(r"(开心|高兴|轻松|难受|焦虑|烦|生气|紧张|崩溃)", s)
    action = re.findall(r"(开始|尝试|决定|完成|推进|复盘|打算|计划)", s)

    traits = []
    if avg_sent_len >= 45:
        traits.append(f"句子偏长（平均{avg_sent_len}字），叙述连续但信息密度较高。")
    else:
        traits.append(f"句长适中（平均{avg_sent_len}字），可读性相对稳定。")
    if len(fillers) >= 6:
        traits.append(f"口语连接词较多（如“然后/就是”共{len(fillers)}次），思路连续但略显绕。")
    elif len(fillers) > 0:
        traits.append(f"存在少量口语连接词（{len(fillers)}次），整体自然。")
    if len(self_repair) > 0:
        traits.append(f"出现自我修正表达（{len(self_repair)}次），反映边说边整理想法。")
    if len(timeline) > 0:
        traits.append(f"时间锚点较充足（{len(timeline)}处），事件回放能力较好。")
    if len(action) > 0:
        traits.append(f"行动词较多（{len(action)}处），叙述中包含执行与复盘倾向。")
    if len(emotion) > 0:
        traits.append(f"情绪词出现{len(emotion)}次，表达强度较高。")
    if not traits:
        traits.append("转写文本较短，暂无法稳定提炼说话特点。")

    return {
        "sample_chars": len(s),
        "sentence_count": sent_count,
        "avg_sentence_len": avg_sent_len,
        "signals": {
            "fillers_count": len(fillers),
            "self_repair_count": len(self_repair),
            "timeline_anchor_count": len(timeline),
            "emotion_word_count": len(emotion),
            "action_word_count": len(action),
        },
        "traits": traits[:6],
    }


def build_audio_file_response(
    *,
    request: Request,
    audio_id: int,
    prefer: str = "raw",
):
    item = get_audio_entry(int(audio_id))
    if not item:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "audio entry not found"})

    file_path = Path(str(item.get("file_path") or "")).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "audio file missing"})

    audio_root = (diaries_dir(request) / "audio").resolve()
    try:
        file_path.relative_to(audio_root)
    except Exception:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PATH", "message": "audio path out of scope"})

    prefer_norm = str(prefer or "raw").strip().lower()
    if prefer_norm == "mp3":
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise HTTPException(status_code=503, detail={"code": "FFMPEG_MISSING", "message": "ffmpeg not found"})
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(file_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-f",
            "mp3",
            "pipe:1",
        ]
        p = subprocess.run(cmd, capture_output=True, check=False)
        if p.returncode != 0 or not p.stdout:
            stderr = (p.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise HTTPException(
                status_code=502,
                detail={"code": "AUDIO_TRANSCODE_FAILED", "message": f"transcode failed: {stderr[:220]}"},
            )
        return Response(content=p.stdout, media_type="audio/mpeg")

    media_type, _enc = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=str(file_path),
        media_type=media_type or "application/octet-stream",
        filename=file_path.name,
    )
