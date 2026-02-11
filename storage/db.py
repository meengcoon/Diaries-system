from __future__ import annotations

"""
storage.db
===========

Compatibility facade over the storage layer.

The original implementation grew into a single "god module" that mixed:
- schema/migrations
- connection helpers
- entries + entry_analysis
- memory cards + change audit
- retrieval (FTS) helpers
- block/job queue + block_analysis

To improve maintainability, the implementation is split into focused modules:
- storage/db_core.py      (connection + schema + shared helpers)
- storage/repo_entries.py (entries + entry_analysis reads/writes)
- storage/repo_mem.py     (mem_cards + mem_card_changes)
- storage/repo_fts.py     (FTS indexing/search)
- storage/repo_jobs.py    (entry_blocks + block_jobs + block_analysis)

This file preserves the original public API by re-exporting functions.
"""

# Core (schema + connection helpers)
from .db_core import (  # noqa: F401
    BASE_DIR,
    DEFAULT_DB_PATH,
    SQLITE_TIMEOUT_S,
    connect,
    transaction,
    get_db_path,
    _connect,
    _safe_json_loads,
    _utc_now_iso,
    _utc_now_dt,
    _fts5_is_available,
    _fts_table_exists,
    init_db,
    compute_sha256,
)

# Entries / analysis
from .repo_entries import (  # noqa: F401
    insert_entry,
    save_entry_analysis,
    list_recent_entries,
    list_recent_entry_summaries,
    get_entry_analysis_brief,
)
from .repo_audio import (  # noqa: F401
    insert_audio_entry,
    list_recent_audio_entries,
    list_recent_audio_analyses,
)

# Memory
from .repo_mem import (  # noqa: F401
    get_mem_card,
    list_mem_cards,
    upsert_mem_card,
    insert_mem_card_change,
    list_mem_card_changes,
)

# Retrieval (FTS)
from .repo_fts import (  # noqa: F401
    upsert_entry_fts,
    search_entry_ids_fts,
)

# Blocks / jobs / per-block analysis
from .repo_jobs import (  # noqa: F401
    insert_entry_block,
    list_entry_blocks,
    count_entry_blocks,
    get_entry_block,
    insert_block_job,
    count_block_jobs_by_status,
    list_pending_block_jobs,
    reset_stale_running_block_jobs,
    claim_next_block_job,
    mark_block_job_ok,
    mark_block_job_failed,
    mark_block_job_skipped,
    upsert_block_analysis,
    get_block_analysis,
    list_entry_blocks_with_analysis,
    get_entry_job_status_summary,
)

# LLM cloud/cache (audit + response cache)
from .repo_llm_calls import (  # noqa: F401
    insert_call,
    get_call,
    list_calls,
)
from .repo_llm_cache import (  # noqa: F401
    is_cache_enabled,
    make_cache_key,
    get_cached_response_json,
    upsert_cached_response_json,
    delete_cache,
    purge_cache_older_than,
)

__all__ = [
    # core
    "BASE_DIR",
    "DEFAULT_DB_PATH",
    "SQLITE_TIMEOUT_S",
    "connect",
    "transaction",
    "get_db_path",
    "_connect",
    "_safe_json_loads",
    "_utc_now_iso",
    "_utc_now_dt",
    "_fts5_is_available",
    "_fts_table_exists",
    "init_db",
    "compute_sha256",
    # entries
    "insert_entry",
    "save_entry_analysis",
    "list_recent_entries",
    "list_recent_entry_summaries",
    "get_entry_analysis_brief",
    # audio
    "insert_audio_entry",
    "list_recent_audio_entries",
    "list_recent_audio_analyses",
    # mem
    "get_mem_card",
    "list_mem_cards",
    "upsert_mem_card",
    "insert_mem_card_change",
    "list_mem_card_changes",
    # fts
    "upsert_entry_fts",
    "search_entry_ids_fts",
    # blocks/jobs
    "insert_entry_block",
    "list_entry_blocks",
    "count_entry_blocks",
    "get_entry_block",
    "insert_block_job",
    "count_block_jobs_by_status",
    "list_pending_block_jobs",
    "reset_stale_running_block_jobs",
    "claim_next_block_job",
    "mark_block_job_ok",
    "mark_block_job_failed",
    "mark_block_job_skipped",
    "upsert_block_analysis",
    "get_block_analysis",
    "list_entry_blocks_with_analysis",
    "get_entry_job_status_summary",
    # llm audit/cache
    "insert_call",
    "get_call",
    "list_calls",
    "is_cache_enabled",
    "make_cache_key",
    "get_cached_response_json",
    "upsert_cached_response_json",
    "delete_cache",
    "purge_cache_older_than",
]
