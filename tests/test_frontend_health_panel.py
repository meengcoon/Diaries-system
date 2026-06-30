from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_frontend(name: str) -> str:
    return (ROOT / "frontend" / name).read_text(encoding="utf-8")


def _slice_between(source: str, start: str, end: str) -> str:
    start_idx = source.index(start)
    end_idx = source.index(end, start_idx)
    return source[start_idx:end_idx]


def test_health_panel_uses_diagnostics_endpoint_not_meta_health():
    app_js = _read_frontend("app.js")

    assert 'fetchJson("/api/health")' in app_js
    assert 'fetchJson("/health")' not in app_js
    assert 'fetch("/health")' not in app_js


def test_health_panel_dom_nodes_exist():
    index_html = _read_frontend("index.html")
    required_ids = [
        "health-status-chip",
        "health-updated",
        "health-error",
        "health-db-path",
        "health-db-counts",
        "health-jobs",
        "health-jobs-detail",
        "health-fts",
        "health-fts-detail",
        "health-rollup",
        "health-rollup-detail",
        "health-context-pack",
        "health-context-pack-detail",
    ]

    for node_id in required_ids:
        assert f'id="{node_id}"' in index_html


def test_health_panel_rendering_does_not_add_raw_html_paths():
    app_js = _read_frontend("app.js")
    health_code = _slice_between(
        app_js,
        "function healthText",
        "async function refreshInsights",
    )

    assert "innerHTML" not in health_code
    assert "dangerouslySetInnerHTML" not in health_code
    assert "marked.parse" not in health_code
