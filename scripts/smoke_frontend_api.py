#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime


def req_json(base_url: str, method: str, path: str, payload: dict | None, timeout: float) -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url=f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {path}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error {path}: {e}") from e


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test frontend-related APIs")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--strict-chat", action="store_true", help="fail when /api/chat is unavailable or times out")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print(f"[INFO] base_url={base_url}")

    health = req_json(base_url, "GET", "/health", None, args.timeout)
    assert_true(health.get("ok") is True, "health.ok should be true")
    print("[PASS] /health")

    bot_info = req_json(base_url, "GET", "/api/_bot", None, args.timeout)
    assert_true("bot" in bot_info, "/api/_bot should contain key 'bot'")
    print(f"[PASS] /api/_bot bot={bot_info.get('bot')}")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    diary_text = f"smoke_frontend_api {stamp}"
    save = req_json(
        base_url,
        "POST",
        "/api/diary/save",
        {"text": diary_text},
        args.timeout,
    )
    assert_true(save.get("ok") is True, "/api/diary/save should return ok=true")
    assert_true("cloud_sync_enabled" in save, "/api/diary/save should expose cloud_sync_enabled")
    file_path = str(save.get("file") or "")
    assert_true(file_path.endswith(".txt"), "save.file should end with .txt")
    date_str = file_path.rsplit("/", 1)[-1].replace(".txt", "")
    print(f"[PASS] /api/diary/save date={date_str} queued_blocks={save.get('queued_blocks')}")

    listing = req_json(base_url, "GET", "/api/diary/list?limit=20", None, args.timeout)
    items = listing.get("items") or []
    assert_true(isinstance(items, list), "/api/diary/list items should be a list")
    assert_true(any(i.get("date") == date_str for i in items), f"date {date_str} should appear in /api/diary/list")
    print("[PASS] /api/diary/list")

    read_path = "/api/diary/read?date=" + urllib.parse.quote(date_str)
    diary = req_json(base_url, "GET", read_path, None, args.timeout)
    text = str(diary.get("text") or "")
    assert_true(diary.get("ok") is True, "/api/diary/read should return ok=true")
    assert_true("smoke_frontend_api" in text, "saved text should be found in /api/diary/read")
    print("[PASS] /api/diary/read")

    sync_existing = req_json(
        base_url,
        "POST",
        "/api/diary/cloud/sync_existing",
        {"limit": 1, "newest_first": True},
        args.timeout,
    )
    assert_true("ok" in sync_existing, "/api/diary/cloud/sync_existing should return ok")
    print("[PASS] /api/diary/cloud/sync_existing")

    sync_state = req_json(base_url, "GET", "/api/diary/cloud/state?limit=5", None, args.timeout)
    assert_true(sync_state.get("ok") is True, "/api/diary/cloud/state should return ok=true")
    print("[PASS] /api/diary/cloud/state")

    try:
        chat = req_json(
            base_url,
            "POST",
            "/api/chat",
            {
                "text": "请回复: smoke ok",
                "mode": "chat",
                "debug": True,
                "preferred_provider": "deepseek",
                "force_local": True,
            },
            args.timeout,
        )
        assert_true("reply" in chat, "/api/chat should contain reply")
        assert_true(chat.get("mode") == "chat", "/api/chat mode should be chat")
        print("[PASS] /api/chat")
    except Exception as e:
        if args.strict_chat:
            raise
        print(f"[WARN] /api/chat skipped: {e}")

    print("[DONE] frontend API smoke passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        raise
