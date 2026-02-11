from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from pipeline.audio_features import analyze_audio_file, build_voice_profile


def _write_test_wav(path: Path, sr: int = 16000) -> None:
    # 1.2s voiced + 0.5s silence + 1.0s voiced
    t1 = np.linspace(0, 1.2, int(sr * 1.2), endpoint=False)
    t2 = np.linspace(0, 1.0, int(sr * 1.0), endpoint=False)
    a = 0.28 * np.sin(2 * np.pi * 220 * t1)
    b = np.zeros(int(sr * 0.5), dtype=np.float32)
    c = 0.34 * np.sin(2 * np.pi * 180 * t2)
    x = np.concatenate([a, b, c]).astype(np.float32)
    x16 = np.clip(x * 32767.0, -32768, 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(x16.tobytes())


def test_analyze_audio_file_wav(tmp_path: Path):
    wav = tmp_path / "sample.wav"
    _write_test_wav(wav)

    out = analyze_audio_file(wav)
    assert out.get("error") is None
    assert float(out.get("duration_s", 0.0)) > 2.5
    assert 0.0 <= float(out.get("voiced_ratio", 0.0)) <= 1.0
    assert float(out.get("pause_ratio", 0.0)) > 0.05
    assert float(out.get("pauses_per_min", 0.0)) >= 0.0


def test_build_voice_profile():
    xs = [
        {"duration_s": 12.4, "voiced_ratio": 0.62, "pause_ratio": 0.38, "pauses_per_min": 14, "syllable_rate_proxy": 2.8, "energy_mean_db": -22.1, "energy_std_db": 4.4},
        {"duration_s": 10.0, "voiced_ratio": 0.58, "pause_ratio": 0.42, "pauses_per_min": 18, "syllable_rate_proxy": 3.0, "energy_mean_db": -21.4, "energy_std_db": 5.0},
    ]
    p = build_voice_profile(xs)
    assert int(p["sample_count"]) == 2
    assert "stats" in p and isinstance(p["stats"], dict)
    assert "habits" in p and isinstance(p["habits"], list) and len(p["habits"]) >= 1
