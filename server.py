from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

_DEFAULT_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_DEFAULT_ENV_PATH, override=False)

# Bot selection: only CascadeBot is supported now.
cascade_import_err: Optional[str] = None
try:
    from bot.cascade_bot import CascadeBot  # type: ignore
except Exception as e:
    CascadeBot = None  # type: ignore
    cascade_import_err = f"{type(e).__name__}: {e}"

from storage.db import init_db  # type: ignore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _resolve_resource_dir() -> Path:
    """Resolve bundled resource directory.

    Priority:
      1) DIARY_RESOURCE_DIR env override
      2) PyInstaller frozen bundle: <App>.app/Contents/Resources
      3) PyInstaller _MEIPASS fallback
      4) Dev mode: directory containing this file
    """
    env = (os.getenv("DIARY_RESOURCE_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()

    if getattr(sys, "frozen", False):
        # Prefer <App>.app/Contents/Resources even when modules live under Contents/Frameworks.
        try:
            here = Path(__file__).resolve()
            # Typical: .../Contents/Frameworks/server.py -> .../Contents/Resources
            for i in range(1, 6):
                cand = here.parents[i] / "Resources"
                if cand.exists():
                    return cand
        except Exception:
            pass
        try:
            exe = Path(sys.executable).resolve()  # .../<App>.app/Contents/MacOS/<App>
            contents_dir = exe.parents[1]         # .../<App>.app/Contents
            resources_dir = contents_dir / "Resources"
            if resources_dir.exists():
                return resources_dir
        except Exception:
            pass

        if hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS")).resolve()

    return Path(__file__).resolve().parent


def _resolve_data_dir(resource_dir: Path) -> Path:
    """Resolve writable user data directory."""
    env = (os.getenv("DIARY_DATA_DIR") or os.getenv("DIARY_BASE_DIR") or "").strip()
    if env:
        path = Path(env).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    if getattr(sys, "frozen", False):
        home = Path.home()
        path = home / "Library" / "Application Support" / "DiarySystem"
        path.mkdir(parents=True, exist_ok=True)
        return path

    return resource_dir


RESOURCE_DIR = _resolve_resource_dir()
DATA_DIR = _resolve_data_dir(RESOURCE_DIR)


def _select_bot() -> object:
    if CascadeBot is not None:
        return CascadeBot()  # type: ignore
    return None


bot = _select_bot()
logger.info(f"server.py loaded from: {__file__}")
logger.info(f"Bot selected: {bot.__class__.__name__}")
if cascade_import_err:
    logger.warning(f"CascadeBot import failed; chat will be unavailable. err={cascade_import_err}")


async def _startup_init(_app: FastAPI) -> None:
    init_db()
    if _app.state.ingest_entry is None:
        logger.error(
            "ingest 未就绪：/api/diary/save 将不可用。"
            f"import_err={_app.state.ingest_import_err}"
        )


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await _startup_init(_app)
    yield


app = FastAPI(title="Personal Diary AI & English Learning", lifespan=_lifespan)

# Share globals with route modules via app.state
app.state.bot = bot
app.state.cascade_import_err = cascade_import_err
app.state.base_dir = RESOURCE_DIR
app.state.resource_dir = RESOURCE_DIR
app.state.data_dir = DATA_DIR


# Step 1: 保存时只做入库 + 切块 + 入队（不再在保存时运行 Phi/Qwen）
try:
    from pipeline.ingest import ingest_entry, InputError  # type: ignore

    app.state.ingest_entry = ingest_entry
    app.state.InputError = InputError
    app.state.ingest_import_err = None
except Exception as e:
    app.state.ingest_entry = None
    app.state.InputError = Exception
    app.state.ingest_import_err = f"{type(e).__name__}: {e}"


def _configure_cors(_app: FastAPI) -> None:
    """Environment-driven CORS.

    - If CORS_ALLOW_ORIGINS is set (comma-separated), use the explicit list.
    - Otherwise, default to localhost/127.0.0.1 only.
    """
    origins_raw = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    origin_regex = (os.getenv("CORS_ALLOW_ORIGIN_REGEX") or "").strip()

    if origins_raw:
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
        _app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info(f"CORS: allow_origins={origins}")
        return

    # Default: only allow local dev origins.
    if not origin_regex:
        origin_regex = r"^https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?$"
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS: allow_origin_regex={origin_regex}")


_configure_cors(app)


# Routers
from api.routes_audio import router as audio_router
from api.routes_chat import router as chat_router
from api.routes_diary import router as diary_router
from api.routes_health import router as health_router
from api.routes_meta import router as meta_router

app.include_router(meta_router)
app.include_router(chat_router)
app.include_router(diary_router)
app.include_router(health_router)
app.include_router(audio_router)


# Static files (must be after API routers)
frontend_dir = RESOURCE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    logger.error(f"frontend directory not found: {frontend_dir} (RESOURCE_DIR={RESOURCE_DIR})")

    @app.get("/", include_in_schema=False)
    async def _missing_frontend_root():
        return (
            "<html><body style='font-family: -apple-system, system-ui; padding: 24px;'>"
            "<h2>Frontend assets not bundled</h2>"
            "<p>The application started, but <code>frontend/</code> was not found inside the app bundle.</p>"
            "<p>Rebuild with PyInstaller using <code>--add-data \\\"frontend:frontend\\\"</code>.</p>"
            "</body></html>"
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = (os.getenv("UVICORN_RELOAD", "0").strip().lower() in {"1", "true", "yes"})

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=reload,
    )
