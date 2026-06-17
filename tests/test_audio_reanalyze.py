from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from services import audio_ingest_service
from storage.repo_audio import get_audio_content_link, insert_audio_entry, upsert_audio_content_link
from storage.repo_entries import get_entry, insert_entry


def test_reanalyze_audio_reuses_existing_entry(monkeypatch, isolated_db, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFFfake")

    entry_id = insert_entry(raw_text="旧内容", source="test")
    old_entry = get_entry(entry_id)
    assert old_entry is not None
    old_version = int(old_entry["version"])

    audio_id = insert_audio_entry(
        diary_date="2026-04-11",
        file_path=str(audio_path),
        source_format="wav",
        duration_s=1.2,
        file_size_bytes=int(audio_path.stat().st_size),
        note="旧备注",
        analysis_json="{}",
    )
    upsert_audio_content_link(audio_entry_id=audio_id, entry_id=entry_id, status="done", provider="deepseek", error=None)

    monkeypatch.setattr(audio_ingest_service, "transcribe_audio_file_local", lambda path: "新的转写内容")
    queued = []
    monkeypatch.setattr(
        audio_ingest_service,
        "queue_entry_analysis",
        lambda **kwargs: queued.append(kwargs) or {"ok": True, "queued": True},
    )

    async def _unexpected_ingest_entry(**kwargs):
        raise AssertionError("reanalyze should reuse existing entry instead of creating a new one")

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(base_dir=Path(tmp_path))))

    res = asyncio.run(
        audio_ingest_service.reanalyze_audio_diary_payload(
            request=request,
            audio_id=int(audio_id),
            preferred_provider="deepseek",
            force_reanalyze=True,
            ingest_entry=_unexpected_ingest_entry,
            input_error_type=ValueError,
        )
    )

    assert res["ok"] is True
    assert int(res["entry_id"]) == int(entry_id)
    assert int(res["queued_blocks"]) > 0
    assert res["cloud_analyze_queued"] is True
    assert len(queued) == 1

    updated_entry = get_entry(entry_id)
    assert updated_entry is not None
    assert int(updated_entry["version"]) == old_version + 1
    assert "新的转写内容" in str(updated_entry["raw_text"])

    link = get_audio_content_link(int(audio_id))
    assert link is not None
    assert int(link["entry_id"]) == int(entry_id)
    assert str(link["status"]) == "done"
