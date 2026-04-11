from __future__ import annotations

import os
import sys
import sqlite3
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "diary.sqlite3"

# SQLite connection timeout (seconds). Helps avoid "database is locked" on brief contention.
SQLITE_TIMEOUT_S = float(os.getenv("SQLITE_TIMEOUT_S", "5"))
# SQLite PRAGMA defaults (can be overridden via env)
SQLITE_JOURNAL_MODE = (os.getenv("DIARY_SQLITE_JOURNAL_MODE", "WAL") or "WAL").strip().upper()
SQLITE_SYNCHRONOUS = (os.getenv("DIARY_SQLITE_SYNCHRONOUS", "NORMAL") or "NORMAL").strip().upper()

def _default_data_dir() -> Path:
    env = (os.getenv("DIARY_DATA_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "DiarySystem"
    if sys.platform.startswith("win"):
        return Path(os.getenv("APPDATA", str(home))) / "DiarySystem"
    return home / ".local" / "share" / "DiarySystem"


def get_db_path() -> Path:
    env = (os.getenv("DIARY_DB_PATH") or "").strip()
    if env:
        return Path(env).expanduser().resolve()

    if getattr(sys, "frozen", False):
        data_dir = _default_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "diary.sqlite3"

    return DEFAULT_DB_PATH

def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Unified connection factory:
    - PRAGMA foreign_keys=ON
    - PRAGMA journal_mode=WAL (default, env overridable)
    - PRAGMA synchronous=NORMAL (default, env overridable)
    - PRAGMA busy_timeout
    """
    path = (db_path or get_db_path()).expanduser().resolve()
    conn = sqlite3.connect(str(path), timeout=SQLITE_TIMEOUT_S)
    conn.row_factory = sqlite3.Row

    # Critical: enforce FK on every connection (SQLite is per-connection)
    conn.execute("PRAGMA foreign_keys=ON;")

    # Helps avoid random "database is locked" under brief contention
    conn.execute(f"PRAGMA busy_timeout={int(SQLITE_TIMEOUT_S * 1000)};")

    # Journal mode (WAL recommended for desktop app)
    try:
        conn.execute(f"PRAGMA journal_mode={SQLITE_JOURNAL_MODE};")
    except sqlite3.OperationalError:
        # Some environments restrict changing journal mode; keep usable.
        pass

    # Synchronous (NORMAL is usually a good local tradeoff)
    if SQLITE_SYNCHRONOUS in {"OFF", "NORMAL", "FULL", "EXTRA"}:
        try:
            conn.execute(f"PRAGMA synchronous={SQLITE_SYNCHRONOUS};")
        except sqlite3.OperationalError:
            pass

    return conn


def _connect() -> sqlite3.Connection:
    # Backward-compatible alias
    return connect()


def _safe_json_loads(s: str) -> Any:
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def _utc_now_iso() -> str:
    """Timezone-aware UTC timestamp for storage."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utc_now_dt() -> datetime:
    """Timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _parse_iso_utc(ts: str) -> Optional[datetime]:
    """Parse an ISO timestamp string; treat naive datetimes as UTC."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


@contextmanager
def _conn_ro():
    """Read-only connection context."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _conn_txn():
    """Read-write connection context with explicit BEGIN/COMMIT/ROLLBACK."""
    conn = connect()
    try:
        conn.execute("BEGIN;")  # explicit transaction boundary
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

@contextmanager
def transaction(db_path: Optional[Path] = None):
    """
    Public transaction context manager.
    Guarantees "single contract fallback = single txn write".
    """
    conn = connect(db_path=db_path)
    try:
        conn.execute("BEGIN;")
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def _fts5_is_available(conn: sqlite3.Connection) -> bool:
    """Best-effort check: return True if FTS5 is usable in this sqlite build."""
    try:
        # If FTS5 is not compiled, creating an fts5 table will raise: no such module: fts5
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS __fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _fts_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entry_fts'"
    ).fetchone()
    return bool(row)


def init_db() -> None:
    """Initialize schema and perform lightweight migrations.

    Note: migrations that need `PRAGMA foreign_keys=OFF` must toggle it *before* BEGIN.
    """

    # --- migration helper: detect if sha256 has a UNIQUE index ---
    def _sha256_is_unique(c: sqlite3.Connection) -> bool:
        rows = c.execute("PRAGMA index_list('entries')").fetchall()
        for r in rows:
            name = r[1]
            unique = int(r[2])
            if unique != 1:
                continue
            cols = c.execute(f"PRAGMA index_info('{name}')").fetchall()
            col_names = [cc[2] for cc in cols]
            if col_names == ["sha256"]:
                return True
        return False

    def _table_columns(c: sqlite3.Connection, table: str) -> List[str]:
        rows = c.execute(f"PRAGMA table_info('{table}')").fetchall()
        return [str(r[1]) for r in rows]

    conn = connect()
    fk_was_disabled = False
    try:
        # Ensure `entries` exists so PRAGMA index_list works on first run.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                source TEXT,
                sha256 TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        cols_entries = _table_columns(conn, "entries")
        if "version" not in cols_entries:
            conn.execute("ALTER TABLE entries ADD COLUMN version INTEGER NOT NULL DEFAULT 1;")

        # Decide whether we need to rebuild `entries` to drop a UNIQUE sha256 index.
        need_migrate_sha256 = _sha256_is_unique(conn)
        if need_migrate_sha256:
            # IMPORTANT: this must happen before BEGIN; toggling inside a txn is unreliable.
            conn.execute("PRAGMA foreign_keys=OFF;")
            fk_was_disabled = True

        # Single atomic init/migration transaction.
        conn.execute("BEGIN;")

        # --- migration: drop UNIQUE constraint on entries.sha256 (v1 -> v2) ---
        if need_migrate_sha256:
            conn.execute("SAVEPOINT migrate_entries_sha256;")
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS entries_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        raw_text TEXT NOT NULL,
                        source TEXT,
                        sha256 TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1
                    );
                    """
                )
                conn.execute(
                    """
                    INSERT INTO entries_new(id, created_at, raw_text, source, sha256, version)
                    SELECT id, created_at, raw_text, source, sha256, COALESCE(version, 1) FROM entries;
                    """
                )
                conn.execute("DROP TABLE entries;")
                conn.execute("ALTER TABLE entries_new RENAME TO entries;")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_sha256 ON entries(sha256);")
                try:
                    conn.execute("DELETE FROM sqlite_sequence WHERE name='entries';")
                    conn.execute(
                        "INSERT INTO sqlite_sequence(name, seq) "
                        "SELECT 'entries', COALESCE(MAX(id),0) FROM entries;"
                    )
                except Exception:
                    pass
                conn.execute("RELEASE migrate_entries_sha256;")
            except Exception:
                conn.execute("ROLLBACK TO migrate_entries_sha256;")
                conn.execute("RELEASE migrate_entries_sha256;")
                raise

        # Ensure indexes exist even when no migration ran.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_sha256 ON entries(sha256);")

        # =====================
        # entry_analysis
        # =====================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entry_analysis (
                entry_id INTEGER PRIMARY KEY,
                analysis_json TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                entry_version INTEGER NOT NULL DEFAULT 1,
                analysis_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
            );
            """
        )
        cols_entry_analysis = _table_columns(conn, "entry_analysis")
        if "entry_version" not in cols_entry_analysis:
            conn.execute("ALTER TABLE entry_analysis ADD COLUMN entry_version INTEGER NOT NULL DEFAULT 1;")
        if "analysis_hash" not in cols_entry_analysis:
            conn.execute("ALTER TABLE entry_analysis ADD COLUMN analysis_hash TEXT NOT NULL DEFAULT '';")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_analysis_created_at ON entry_analysis(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_analysis_entry_version ON entry_analysis(entry_version);")

        # =====================
        # M3: Retrieval (FTS5)
        # =====================
        try:
            if _fts5_is_available(conn):
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5(
                        entry_id UNINDEXED,
                        created_at UNINDEXED,
                        summary_1_3,
                        topics,
                        facts,
                        todos
                    );
                    """
                )
        except sqlite3.OperationalError:
            pass

        # =====================
        # M2: mem_cards + changes
        # =====================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mem_cards (
                card_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                confidence REAL NOT NULL
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mem_card_changes (
                change_id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id TEXT NOT NULL,
                entry_id INTEGER NOT NULL,
                diff_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES mem_cards(card_id) ON DELETE CASCADE,
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
            );
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_cards_type ON mem_cards(type);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_cards_updated_at ON mem_cards(updated_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_card_changes_card_id ON mem_card_changes(card_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_card_changes_entry_id ON mem_card_changes(entry_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_card_changes_created_at ON mem_card_changes(created_at);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_update_applied (
                entry_id INTEGER NOT NULL,
                entry_version INTEGER NOT NULL,
                analysis_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(entry_id, entry_version),
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_update_applied_hash ON memory_update_applied(analysis_hash, created_at);"
        )

        # =====================
        # Step 1: entry_blocks + jobs
        # =====================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entry_blocks (
                block_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                idx INTEGER NOT NULL,
                title TEXT,
                raw_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE,
                UNIQUE(entry_id, idx)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_blocks_entry_id ON entry_blocks(entry_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_blocks_created_at ON entry_blocks(created_at);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS block_jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_id INTEGER NOT NULL,
                entry_version INTEGER NOT NULL DEFAULT 1,
                dedupe_key TEXT,
                status TEXT NOT NULL,         -- pending|running|done|failed|skipped
                attempts INTEGER NOT NULL,
                last_error TEXT,
                leased_by TEXT,
                leased_until TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(block_id) REFERENCES entry_blocks(block_id) ON DELETE CASCADE,
                UNIQUE(block_id)
            );
            """
        )
        cols_block_jobs = _table_columns(conn, "block_jobs")
        if "entry_version" not in cols_block_jobs:
            conn.execute("ALTER TABLE block_jobs ADD COLUMN entry_version INTEGER NOT NULL DEFAULT 1;")
        if "dedupe_key" not in cols_block_jobs:
            conn.execute("ALTER TABLE block_jobs ADD COLUMN dedupe_key TEXT;")
        if "leased_by" not in cols_block_jobs:
            conn.execute("ALTER TABLE block_jobs ADD COLUMN leased_by TEXT;")
        if "leased_until" not in cols_block_jobs:
            conn.execute("ALTER TABLE block_jobs ADD COLUMN leased_until TEXT;")
        conn.execute(
            """
            UPDATE block_jobs
            SET entry_version = COALESCE(
                (
                    SELECT e.version
                    FROM entry_blocks b
                    JOIN entries e ON e.id = b.entry_id
                    WHERE b.block_id = block_jobs.block_id
                ),
                1
            )
            WHERE COALESCE(entry_version, 0) <= 0
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_block_jobs_status ON block_jobs(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_block_jobs_updated_at ON block_jobs(updated_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_block_jobs_lease ON block_jobs(status, leased_until, updated_at);")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_block_jobs_dedupe_key ON block_jobs(dedupe_key) WHERE dedupe_key IS NOT NULL;"
        )

        # =====================
        # Step 2: block_analysis
        # =====================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS block_analysis (
                block_id INTEGER PRIMARY KEY,
                analysis_json TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ok INTEGER NOT NULL,
                error TEXT,
                FOREIGN KEY(block_id) REFERENCES entry_blocks(block_id) ON DELETE CASCADE
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_block_analysis_created_at ON block_analysis(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_block_analysis_ok ON block_analysis(ok);")

        # =====================
        # Step 2b: staged analysis runs (intermediate evidence/deep/normalize records)
        # =====================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,      -- block|entry
                target_id INTEGER NOT NULL,
                stage TEXT NOT NULL,            -- evidence|deep|normalize|validate|final
                backend TEXT NOT NULL,          -- local|cloud|rollup
                provider TEXT,
                model TEXT,
                prompt_version TEXT NOT NULL,
                status TEXT NOT NULL,           -- ok|failed|rejected
                input_json TEXT,
                output_json TEXT,
                error TEXT,
                ms INTEGER,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_runs_target ON analysis_runs(target_type, target_id, created_at DESC);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_runs_stage_status ON analysis_runs(stage, status, created_at DESC);"
        )

        # =====================
        # LLM cache + call auditing
        # =====================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_cache_provider_model ON llm_cache(provider, model);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_cache_updated_at ON llm_cache(updated_at);")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                request_json TEXT,
                response_json TEXT,
                status TEXT NOT NULL, -- ok|failed
                error TEXT,
                ms INTEGER,
                tokens_prompt INTEGER,
                tokens_completion INTEGER,
                tokens_total INTEGER
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_created_at ON llm_calls(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_provider_status ON llm_calls(provider, status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_request_hash ON llm_calls(request_hash);")

        # =====================
        # Chat sessions + messages
        # =====================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                pinned INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions(updated_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_pinned ON chat_sessions(pinned, updated_at);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL, -- user|assistant|system
                mode TEXT NOT NULL, -- chat|voice_chat
                text TEXT NOT NULL,
                meta_json TEXT,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL
            );
            """
        )
        cols_chat_messages = _table_columns(conn, "chat_messages")
        if "session_id" not in cols_chat_messages:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN session_id INTEGER;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_role_mode ON chat_messages(role, mode);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id, created_at);")

        legacy_count_row = conn.execute(
            "SELECT COUNT(1) AS n FROM chat_messages WHERE session_id IS NULL"
        ).fetchone()
        legacy_count = int(legacy_count_row["n"] if legacy_count_row else 0)
        if legacy_count > 0:
            legacy_session = conn.execute(
                "SELECT id FROM chat_sessions WHERE title='历史对话' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if legacy_session:
                legacy_session_id = int(legacy_session["id"])
            else:
                now = _utc_now_iso()
                cur = conn.execute(
                    """
                    INSERT INTO chat_sessions(created_at, updated_at, title, summary)
                    VALUES(?,?,?,?)
                    """,
                    (now, now, "历史对话", "旧版本迁移过来的聊天记录"),
                )
                legacy_session_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE chat_messages SET session_id=? WHERE session_id IS NULL",
                (legacy_session_id,),
            )
            last_row = conn.execute(
                """
                SELECT MAX(created_at) AS updated_at
                FROM chat_messages
                WHERE session_id=?
                """,
                (legacy_session_id,),
            ).fetchone()
            updated_at = str(last_row["updated_at"] or _utc_now_iso()) if last_row else _utc_now_iso()
            conn.execute(
                "UPDATE chat_sessions SET updated_at=? WHERE id=?",
                (updated_at, legacy_session_id),
            )

        # =====================
        # Voice diary: raw audio + feature analysis
        # =====================
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audio_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                diary_date TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                source_format TEXT NOT NULL,
                duration_s REAL,
                file_size_bytes INTEGER NOT NULL,
                note TEXT,
                analysis_json TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_entries_created_at ON audio_entries(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_entries_diary_date ON audio_entries(diary_date);")

        # Track whether audio content has been transcribed/ingested for cloud text analysis.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audio_content_links (
                audio_entry_id INTEGER PRIMARY KEY,
                entry_id INTEGER,
                status TEXT NOT NULL, -- pending|done|failed
                provider TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(audio_entry_id) REFERENCES audio_entries(id) ON DELETE CASCADE,
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE SET NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_content_links_status ON audio_content_links(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_content_links_entry_id ON audio_content_links(entry_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_content_links_updated_at ON audio_content_links(updated_at);")

        conn.commit()

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

    finally:
        # Re-enable FK checks after migrations. Must be outside the active transaction.
        if fk_was_disabled:
            try:
                conn.execute("PRAGMA foreign_keys=ON;")
            except Exception:
                pass
        conn.close()


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
