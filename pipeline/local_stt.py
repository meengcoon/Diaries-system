from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from utils.ffmpeg import find_ffmpeg


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _ffmpeg_to_wav(src: Path) -> Path:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    tmp = tempfile.NamedTemporaryFile(prefix="local_stt_", suffix=".wav", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(tmp_path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        err = (p.stderr or "").strip()
        raise RuntimeError(f"ffmpeg convert failed: {err[:220]}")
    return tmp_path


def _transcribe_with_faster_whisper(wav_path: Path, model_name: str, device: str, compute_type: str) -> str:
    from faster_whisper import WhisperModel  # type: ignore

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(str(wav_path), vad_filter=True)
    text = " ".join((s.text or "").strip() for s in segments).strip()
    return text


def transcribe_audio_file_local(audio_path: Path) -> str:
    path = Path(audio_path).expanduser().resolve()
    if not path.exists():
        raise RuntimeError("audio file missing")

    model_name = _env("LOCAL_STT_MODEL", "small")
    device = _env("LOCAL_STT_DEVICE", "auto")
    compute_type = _env("LOCAL_STT_COMPUTE_TYPE", "int8")

    wav_path: Path | None = None
    try:
        if path.suffix.lower() == ".wav":
            wav_path = path
        else:
            wav_path = _ffmpeg_to_wav(path)

        text = _transcribe_with_faster_whisper(wav_path, model_name, device, compute_type)

        text = (text or "").strip()
        if not text:
            raise RuntimeError("stt_empty_result")
        return text
    finally:
        if wav_path is not None and wav_path != path:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
