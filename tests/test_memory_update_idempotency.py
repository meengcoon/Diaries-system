from __future__ import annotations

import asyncio

from pipeline import memory_update
from storage.repo_entries import insert_entry


def test_update_mem_cards_for_entry_is_idempotent_for_same_analysis(monkeypatch, isolated_db):
    entry_id = insert_entry(raw_text="我最近总是在想工作节奏。", source="test")
    calls = {"n": 0}

    async def _fake_update_mem_cards(*, entry_id, analysis_json, client=None, model=None, top_n=5):
        calls["n"] += 1
        return {
            "ok": True,
            "updated": 1,
            "changes": 1,
            "card_ids": ["chat_profile:general"],
            "candidates": 1,
            "prompt_version": "mem_test",
            "ms": 1,
            "error": None,
        }

    monkeypatch.setattr(memory_update, "update_mem_cards", _fake_update_mem_cards)

    payload = {
        "summary_1_3": "最近工作节奏有点乱。",
        "topics": ["work"],
        "facts": ["最近经常思考工作节奏"],
    }

    first = asyncio.run(
        memory_update.update_mem_cards_for_entry(
            entry_id=entry_id,
            entry_analysis=payload,
            entry_version=2,
            analysis_hash="hash-1",
            client=None,
        )
    )
    second = asyncio.run(
        memory_update.update_mem_cards_for_entry(
            entry_id=entry_id,
            entry_analysis=payload,
            entry_version=2,
            analysis_hash="hash-1",
            client=None,
        )
    )

    assert calls["n"] == 1
    assert first["ok"] is True
    assert first["entry_version"] == 2
    assert first["analysis_hash"] == "hash-1"
    assert second["ok"] is True
    assert second["attempted"] is False
    assert second["skipped_reason"] == "already_applied"
    assert second["entry_version"] == 2
    assert second["analysis_hash"] == "hash-1"
