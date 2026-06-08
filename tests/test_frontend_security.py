from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ai_chat_messages_do_not_render_raw_markdown_html():
    app_js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "marked.parse" not in app_js
    assert "cdn.jsdelivr.net/npm/marked" not in index_html
    assert "body.textContent = text || \"\";" in app_js
