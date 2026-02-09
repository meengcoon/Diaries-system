from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health():
    """Basic health check for smoke tests and deployment probes."""
    return {"ok": True}


@router.get("/api/_bot")
async def bot_info(request: Request):
    bot = getattr(request.app.state, "bot", None)
    cascade_import_err = getattr(request.app.state, "cascade_import_err", None)
    return {
        "bot": getattr(bot, "__class__", type("X", (), {})).__name__ if bot else None,
        "cascade_import_err": cascade_import_err,
        "server_file": str(Path(__file__).resolve()),
    }


@router.get("/api/_routes")
async def routes_info(request: Request):
    app = request.app
    return {
        "routes": [
            {
                "path": getattr(r, "path", None),
                "name": getattr(r, "name", None),
                "methods": sorted(list(getattr(r, "methods", []) or [])),
            }
            for r in app.router.routes
        ]
    }
