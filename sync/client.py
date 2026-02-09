from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .crypto import (
    DeviceKeyPair,
    decrypt_json,
    encrypt_json,
    generate_device_keypair,
    generate_group_key,
    open_group_key_for_device,
    seal_group_key_for_device,
)
from .events import build_event_v1


class LocalSyncService:
    """A minimal encrypted event relay.

    The service stores only ciphertext/events and key envelopes.
    It does not keep plaintext group keys.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path).expanduser())
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sync_devices (
                    device_id TEXT PRIMARY KEY,
                    public_key_b64 TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
                );
                CREATE TABLE IF NOT EXISTS sync_key_envelopes (
                    group_key_version INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    PRIMARY KEY(group_key_version, device_id)
                );
                CREATE TABLE IF NOT EXISTS sync_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    group_key_version INTEGER NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    box_json TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def register_device(self, *, device_id: str, public_key_b64: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO sync_devices(device_id, public_key_b64, revoked)
                VALUES(?,?,0)
                ON CONFLICT(device_id) DO UPDATE SET public_key_b64=excluded.public_key_b64, revoked=0
                """,
                (device_id, public_key_b64),
            )
            conn.commit()
        finally:
            conn.close()

    def revoke_device(self, *, device_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE sync_devices SET revoked=1 WHERE device_id=?", (device_id,))
            conn.commit()
        finally:
            conn.close()

    def list_active_devices(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT device_id, public_key_b64 FROM sync_devices WHERE revoked=0 ORDER BY device_id ASC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def put_key_envelope(self, *, group_key_version: int, device_id: str, envelope: Dict[str, str]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO sync_key_envelopes(group_key_version, device_id, envelope_json)
                VALUES(?,?,?)
                ON CONFLICT(group_key_version, device_id) DO UPDATE SET envelope_json=excluded.envelope_json
                """,
                (int(group_key_version), str(device_id), json.dumps(envelope, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_key_envelope(self, *, group_key_version: int, device_id: str) -> Optional[Dict[str, str]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT envelope_json FROM sync_key_envelopes WHERE group_key_version=? AND device_id=?",
                (int(group_key_version), str(device_id)),
            ).fetchone()
            if not row:
                return None
            return json.loads(row["envelope_json"])
        finally:
            conn.close()

    def latest_group_key_version(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute("SELECT COALESCE(MAX(group_key_version), 0) AS v FROM sync_key_envelopes").fetchone()
            return int(row["v"] if row else 0)
        finally:
            conn.close()

    def put_event(self, *, event_obj: Dict[str, Any], box: Dict[str, str]) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO sync_events(event_id, group_key_version, entity_type, entity_id, event_json, box_json)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    str(event_obj["event_id"]),
                    int(event_obj["group_key_version"]),
                    str(event_obj["entity_type"]),
                    str(event_obj["entity_id"]),
                    json.dumps(event_obj, ensure_ascii=False, sort_keys=True),
                    json.dumps(box, ensure_ascii=False, sort_keys=True),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def list_events_since(self, *, seq: int = 0) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT seq, event_json, box_json, group_key_version
                FROM sync_events
                WHERE seq > ?
                ORDER BY seq ASC
                """,
                (int(seq),),
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    {
                        "seq": int(r["seq"]),
                        "group_key_version": int(r["group_key_version"]),
                        "event": json.loads(r["event_json"]),
                        "box": json.loads(r["box_json"]),
                    }
                )
            return out
        finally:
            conn.close()


class SyncClient:
    def __init__(self, *, service: LocalSyncService, device_id: str, keys: DeviceKeyPair | None = None) -> None:
        self.service = service
        self.device_id = str(device_id)
        self.keys = keys or generate_device_keypair()
        self._group_keys: Dict[int, bytes] = {}
        self._last_seq = 0

        self.service.register_device(device_id=self.device_id, public_key_b64=self.keys.public_key_b64)

    @property
    def group_key_version(self) -> int:
        if not self._group_keys:
            return 0
        return max(self._group_keys.keys())

    def bootstrap_group(self) -> int:
        if self.service.latest_group_key_version() > 0:
            return self.fetch_latest_key()
        key = generate_group_key()
        version = 1
        env = seal_group_key_for_device(group_key=key, device_public_key_b64=self.keys.public_key_b64)
        self.service.put_key_envelope(group_key_version=version, device_id=self.device_id, envelope=env)
        self._group_keys[version] = key
        return version

    def fetch_latest_key(self) -> int:
        latest = self.service.latest_group_key_version()
        if latest <= 0:
            return 0
        self.fetch_key(version=latest)
        return latest

    def fetch_key(self, *, version: int) -> bool:
        env = self.service.get_key_envelope(group_key_version=int(version), device_id=self.device_id)
        if not env:
            return False
        key = open_group_key_for_device(envelope=env, device_private_key_b64=self.keys.private_key_b64)
        self._group_keys[int(version)] = key
        return True

    def share_key_with_device(self, *, target_device_id: str, target_public_key_b64: str, version: int | None = None) -> None:
        v = int(version or self.group_key_version)
        if v <= 0 or v not in self._group_keys:
            raise ValueError("group key not available")
        env = seal_group_key_for_device(group_key=self._group_keys[v], device_public_key_b64=target_public_key_b64)
        self.service.put_key_envelope(group_key_version=v, device_id=target_device_id, envelope=env)

    def rotate_group_key(self) -> int:
        new_v = int(self.service.latest_group_key_version()) + 1
        new_key = generate_group_key()

        active = self.service.list_active_devices()
        for d in active:
            env = seal_group_key_for_device(group_key=new_key, device_public_key_b64=str(d["public_key_b64"]))
            self.service.put_key_envelope(group_key_version=new_v, device_id=str(d["device_id"]), envelope=env)

        self._group_keys[new_v] = new_key
        return new_v

    def push_event(
        self,
        *,
        entity_type: str,
        entity_id: str,
        op: str,
        payload: Dict[str, Any],
        deps: List[str] | None = None,
        base_version: int = 0,
    ) -> Dict[str, Any]:
        v = self.group_key_version or self.fetch_latest_key()
        if v <= 0:
            raise ValueError("group key is not initialized")
        key = self._group_keys[v]
        evt = build_event_v1(
            device_id=self.device_id,
            group_key_version=v,
            entity_type=entity_type,
            entity_id=entity_id,
            op=op,
            payload=payload,
            deps=deps,
            base_version=base_version,
        )
        aad = {"event_id": evt["event_id"], "group_key_version": v}
        box = encrypt_json(key=key, payload=evt, aad=aad)
        self.service.put_event(event_obj=evt, box=box)
        return evt

    def pull_events(self) -> List[Dict[str, Any]]:
        rows = self.service.list_events_since(seq=self._last_seq)
        out: List[Dict[str, Any]] = []
        for row in rows:
            seq = int(row["seq"])
            evt = row["event"]
            v = int(row["group_key_version"])
            if v not in self._group_keys:
                self.fetch_key(version=v)
            key = self._group_keys.get(v)
            if not key:
                self._last_seq = max(self._last_seq, seq)
                continue

            aad = {"event_id": evt["event_id"], "group_key_version": v}
            try:
                dec = decrypt_json(key=key, box=row["box"], aad=aad)
                out.append(dec)
            finally:
                self._last_seq = max(self._last_seq, seq)
        return out
