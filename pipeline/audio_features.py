from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


def _to_float32_pcm(raw: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        x = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        return (x - 128.0) / 128.0
    if sample_width == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        return x / 32768.0
    if sample_width == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        return x / 2147483648.0
    raise ValueError(f"unsupported sample width: {sample_width}")


def _read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        n_channels = int(wf.getnchannels())
        sample_width = int(wf.getsampwidth())
        sample_rate = int(wf.getframerate())
        n_frames = int(wf.getnframes())
        raw = wf.readframes(n_frames)

    x = _to_float32_pcm(raw, sample_width)
    if n_channels > 1:
        x = x.reshape(-1, n_channels).mean(axis=1)
    return x, sample_rate


def _ffmpeg_to_wav(src: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    tmp = tempfile.NamedTemporaryFile(prefix="diary_audio_", suffix=".wav", delete=False)
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
        stderr = (p.stderr or "").strip()
        raise RuntimeError(f"ffmpeg convert failed: {stderr[:220]}")
    return tmp_path


def _run_lengths(mask: np.ndarray) -> List[tuple[bool, int]]:
    if mask.size == 0:
        return []
    out: List[tuple[bool, int]] = []
    cur = bool(mask[0])
    count = 1
    for v in mask[1:]:
        vb = bool(v)
        if vb == cur:
            count += 1
            continue
        out.append((cur, count))
        cur = vb
        count = 1
    out.append((cur, count))
    return out


def _count_peaks(xs: np.ndarray, min_distance: int, threshold: float) -> int:
    if xs.size < 3:
        return 0
    d = np.diff(xs)
    idx = np.where((d[:-1] > 0) & (d[1:] <= 0))[0] + 1
    idx = idx[xs[idx] >= threshold]
    if idx.size == 0:
        return 0

    kept = [int(idx[0])]
    for i in idx[1:]:
        if int(i) - kept[-1] >= int(min_distance):
            kept.append(int(i))
    return len(kept)


def analyze_audio_file(audio_path: Path) -> Dict[str, Any]:
    path = Path(audio_path).expanduser().resolve()
    ext = path.suffix.lower()
    file_size = int(path.stat().st_size) if path.exists() else 0

    tmp_wav: Path | None = None
    working = path
    backend = "wav-direct"

    try:
        if ext != ".wav":
            tmp_wav = _ffmpeg_to_wav(path)
            working = tmp_wav
            backend = "ffmpeg"

        x, sr = _read_wav_mono(working)
        if x.size == 0:
            raise ValueError("empty audio")

        duration_s = float(x.size / max(sr, 1))
        frame_len = max(1, int(0.03 * sr))   # 30ms
        hop = max(1, int(0.01 * sr))         # 10ms
        frame_count = 1 + max(0, (x.size - frame_len) // hop)
        if frame_count <= 0:
            frame_count = 1

        rms = np.zeros(frame_count, dtype=np.float32)
        zcr = np.zeros(frame_count, dtype=np.float32)

        for i in range(frame_count):
            s = i * hop
            e = min(x.size, s + frame_len)
            f = x[s:e]
            if f.size == 0:
                continue
            rms[i] = float(np.sqrt(np.mean(np.square(f)) + 1e-12))
            sign = np.sign(f)
            zcr[i] = float(np.mean(np.abs(np.diff(sign)) > 0))

        rms_db = 20.0 * np.log10(np.maximum(rms, 1e-8))
        noise_floor = float(np.percentile(rms_db, 15))
        voice_threshold = noise_floor + 10.0
        voiced = rms_db >= voice_threshold

        voiced_ratio = float(np.mean(voiced)) if voiced.size else 0.0
        pause_ratio = float(1.0 - voiced_ratio)

        runs = _run_lengths(voiced)
        pause_count = 0
        speech_count = 0
        pauses_total_s = 0.0
        speech_total_s = 0.0
        min_pause_frames = max(1, int(0.30 / (hop / sr)))
        min_speech_frames = max(1, int(0.20 / (hop / sr)))
        for is_voiced, n in runs:
            seg_s = n * hop / sr
            if is_voiced:
                if n >= min_speech_frames:
                    speech_count += 1
                    speech_total_s += seg_s
            else:
                if n >= min_pause_frames:
                    pause_count += 1
                    pauses_total_s += seg_s

        voiced_rms_db = rms_db[voiced] if np.any(voiced) else rms_db
        energy_mean_db = float(np.mean(voiced_rms_db)) if voiced_rms_db.size else float(np.mean(rms_db))
        energy_std_db = float(np.std(voiced_rms_db)) if voiced_rms_db.size else float(np.std(rms_db))

        norm_rms = (rms - np.min(rms)) / (np.ptp(rms) + 1e-8)
        peak_count = _count_peaks(norm_rms, min_distance=max(1, int(0.12 / (hop / sr))), threshold=0.55)
        syllable_rate_proxy = float(peak_count / max(duration_s, 1e-3))
        pauses_per_min = float(pause_count / max(duration_s / 60.0, 1e-3))

        return {
            "analysis_version": "voice-v1",
            "backend": backend,
            "source_ext": ext or "",
            "file_size_bytes": file_size,
            "sample_rate_hz": int(sr),
            "duration_s": round(duration_s, 3),
            "frame_hop_ms": int(round(hop * 1000 / sr)),
            "voiced_ratio": round(voiced_ratio, 4),
            "pause_ratio": round(pause_ratio, 4),
            "pause_count": int(pause_count),
            "speech_segment_count": int(speech_count),
            "pauses_per_min": round(pauses_per_min, 3),
            "speech_total_s": round(speech_total_s, 3),
            "pause_total_s": round(pauses_total_s, 3),
            "energy_mean_db": round(energy_mean_db, 3),
            "energy_std_db": round(energy_std_db, 3),
            "zcr_mean": round(float(np.mean(zcr)) if zcr.size else 0.0, 6),
            "zcr_std": round(float(np.std(zcr)) if zcr.size else 0.0, 6),
            "syllable_rate_proxy": round(syllable_rate_proxy, 3),
        }
    except Exception as e:
        return {
            "analysis_version": "voice-v1",
            "backend": backend,
            "source_ext": ext or "",
            "file_size_bytes": file_size,
            "error": f"{type(e).__name__}: {e}",
        }
    finally:
        if tmp_wav is not None:
            try:
                tmp_wav.unlink(missing_ok=True)
            except Exception:
                pass


def build_voice_profile(analysis_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    cleaned = []
    for it in analysis_items or []:
        if not isinstance(it, dict):
            continue
        if it.get("error"):
            continue
        if not isinstance(it.get("duration_s"), (int, float)):
            continue
        cleaned.append(it)

    if not cleaned:
        return {
            "sample_count": 0,
            "habits": ["样本不足，继续记录几段语音后可得到稳定画像"],
            "stats": {},
        }

    def avg(key: str) -> float:
        vals = [float(x.get(key)) for x in cleaned if isinstance(x.get(key), (int, float))]
        if not vals:
            return 0.0
        return float(sum(vals) / len(vals))

    stats = {
        "avg_duration_s": round(avg("duration_s"), 3),
        "avg_voiced_ratio": round(avg("voiced_ratio"), 4),
        "avg_pause_ratio": round(avg("pause_ratio"), 4),
        "avg_pauses_per_min": round(avg("pauses_per_min"), 3),
        "avg_syllable_rate_proxy": round(avg("syllable_rate_proxy"), 3),
        "avg_energy_mean_db": round(avg("energy_mean_db"), 3),
        "avg_energy_std_db": round(avg("energy_std_db"), 3),
    }

    habits: List[str] = []
    pause_ratio = stats["avg_pause_ratio"]
    syll_rate = stats["avg_syllable_rate_proxy"]
    pauses_per_min = stats["avg_pauses_per_min"]
    energy_std = stats["avg_energy_std_db"]
    energy_mean = stats["avg_energy_mean_db"]

    if pause_ratio >= 0.45:
        habits.append("停顿较多，通常会边想边说，表达更谨慎")
    elif pause_ratio <= 0.20:
        habits.append("语流连续度高，表达较顺畅")
    else:
        habits.append("停顿与连贯度均衡，表达节奏稳定")

    if syll_rate >= 4.0:
        habits.append("语速偏快，信息密度较高")
    elif syll_rate <= 2.0:
        habits.append("语速偏慢，叙述更从容")
    else:
        habits.append("语速中等，便于持续记录")

    if pauses_per_min >= 25:
        habits.append("句间切分较频繁，可能偏短句表达")
    elif pauses_per_min <= 10:
        habits.append("句间切分较少，偏连续叙述")

    if energy_std >= 6.5:
        habits.append("音量波动较明显，情绪起伏可能更易体现在语音里")
    elif energy_std <= 3.0:
        habits.append("音量较稳定，说话风格偏平稳")

    if energy_mean <= -30:
        habits.append("平均音量偏低，录音时可更靠近麦克风")

    # 去重并保持顺序
    dedup = []
    seen = set()
    for h in habits:
        if h in seen:
            continue
        seen.add(h)
        dedup.append(h)

    return {
        "sample_count": len(cleaned),
        "stats": stats,
        "habits": dedup or ["当前语音特征较稳定，可继续累积样本观察趋势"],
    }
