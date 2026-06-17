from __future__ import annotations

import pytest

from storage.db_core import init_db


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("DIARY_DB_PATH", str(db_path))
    init_db()
    return db_path
