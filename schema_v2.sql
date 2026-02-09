-- schema_v2.sql
-- SQLite schema v2 (JSON1 required)
-- Goals:
--   - batches 不允许级联删除（RESTRICT / NO ACTION）
--   - memo_cards.trigger_condition JSON 强约束 + 默认值
--   - memo_cards.updated_at 自动更新（trigger）
--   - life_events.event_ts > 0 / block_id 不能是 "le:" 空后缀
--   - memo_ops 加 batch_id/card_key 索引

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ================
-- batches：批次锚点（审计锚点，绝不级联删除）
-- ================
CREATE TABLE IF NOT EXISTS batches (
  batch_id         TEXT PRIMARY KEY,                  -- UUID/雪花等均可
  contract_version TEXT NOT NULL,                     -- e.g. "v1"
  model_provider   TEXT,
  model_name       TEXT,
  source           TEXT,
  created_at       INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  CHECK (length(batch_id) >= 8)
);

-- ================
-- memo_cards：长期记忆卡
-- ================
CREATE TABLE IF NOT EXISTS memo_cards (
  card_key           TEXT PRIMARY KEY,                -- e.g. "mc:persona.core"
  card_type          TEXT NOT NULL,
  content_json       TEXT NOT NULL,
  trigger_condition  TEXT NOT NULL DEFAULT '{}',       -- 必须：默认值 + JSON 约束
  confidence         REAL NOT NULL DEFAULT 0.5,
  created_at         INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
  updated_at         INTEGER NOT NULL DEFAULT (CAST((julianday('now')-2440587.5)*8640000 AS INTEGER)),

  -- content_json：一般要求 object（你如果要允许 array，可以改成 IN ('object','array')）
  CHECK (json_valid(content_json) AND json_type(content_json) = 'object'),

  -- 必须：trigger_condition JSON 强化（object/array 均可）
  CHECK (json_valid(trigger_condition) AND json_type(trigger_condition) IN ('object','array')),

  CHECK (instr(card_key, ':') > 0)
);

-- 必须：updated_at 自动更新（避免“看起来没更新”）
-- 使用 AFTER UPDATE + WHEN 防递归/防覆盖（如果你显式 set updated_at，这个 trigger 不会抢写）
CREATE TRIGGER IF NOT EXISTS trg_memo_cards_updated_at
AFTER UPDATE ON memo_cards
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
  UPDATE memo_cards
  SET updated_at = CAST(strftime('%s','now') AS INTEGER)
  WHERE card_key = NEW.card_key;
END;

-- ================
-- life_events：事件表（证据链要引用它的 block_id）
-- ================
CREATE TABLE IF NOT EXISTS life_events (
  event_id       TEXT PRIMARY KEY,
  batch_id       TEXT NOT NULL,
  block_id       TEXT NOT NULL,                        -- 必须：le:<suffix> 且 suffix 非空
  event_ts       INTEGER NOT NULL,                     -- 必须：>0
  event_type     TEXT NOT NULL,
  summary        TEXT,
  tags           TEXT NOT NULL DEFAULT '[]',           -- JSON array
  evidence_refs  TEXT NOT NULL DEFAULT '[]',           -- JSON array
  confidence     REAL NOT NULL DEFAULT 0.5,
  created_at     INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),

  -- 必须：禁止 batches 级联删除
  FOREIGN KEY (batch_id) REFERENCES batches(batch_id) ON DELETE RESTRICT,

  -- 强烈建议：event_ts > 0
  CHECK (event_ts > 0),

  -- 强烈建议：block_id 不能是 "le:"（空允许会直接把证据路由搞穿）
  CHECK (substr(block_id, 1, 3) = 'le:' AND length(block_id) > 3),

  CHECK (json_valid(tags) AND json_type(tags) = 'array'),
  CHECK (json_valid(evidence_refs) AND json_type(evidence_refs) = 'array')
);

-- ================
-- memo_ops：记忆更新操作（可审计、可回放）
-- ================
CREATE TABLE IF NOT EXISTS memo_ops (
  op_id         TEXT PRIMARY KEY,
  batch_id      TEXT NOT NULL,
  card_key      TEXT NOT NULL,
  op_type       TEXT NOT NULL,                         -- app 层约束枚举
  payload_json  TEXT NOT NULL,
  evidence_refs TEXT NOT NULL DEFAULT '[]',
  created_at    INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),

  -- 必须：禁止 batches 级联删除
  FOREIGN KEY (batch_id) REFERENCES batches(batch_id) ON DELETE RESTRICT,

  CHECK (json_valid(payload_json) AND json_type(payload_json) IN ('object','array')),
  CHECK (json_valid(evidence_refs) AND json_type(evidence_refs) = 'array')
);

-- ================
-- changes：审计变化记录（append-only）
-- ================
CREATE TABLE IF NOT EXISTS changes (
  change_id    TEXT PRIMARY KEY,
  batch_id     TEXT NOT NULL,
  entity_type  TEXT NOT NULL,                          -- life_events/memo_ops/memo_cards/...
  entity_id    TEXT NOT NULL,
  action       TEXT NOT NULL,                          -- create/update/delete
  diff_json    TEXT NOT NULL DEFAULT '{}',
  created_at   INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),

  -- 必须：禁止 batches 级联删除
  FOREIGN KEY (batch_id) REFERENCES batches(batch_id) ON DELETE RESTRICT,

  CHECK (json_valid(diff_json) AND json_type(diff_json) = 'object')
);

-- ================
-- 索引（你要求的 + 审计/检索常用）
-- ================
-- 强烈建议：life_events.event_ts 查时间线必须走索引
CREATE INDEX IF NOT EXISTS idx_life_events_event_ts ON life_events(event_ts);
CREATE INDEX IF NOT EXISTS idx_life_events_batch_id ON life_events(batch_id);

-- 强烈建议：memo_ops(batch_id / card_key)
CREATE INDEX IF NOT EXISTS idx_memo_ops_batch_id ON memo_ops(batch_id);
CREATE INDEX IF NOT EXISTS idx_memo_ops_card_key ON memo_ops(card_key);

-- changes：按 batch 回溯通常是 batch_id + created_at
CREATE INDEX IF NOT EXISTS idx_changes_batch_id_created_at ON changes(batch_id, created_at);

-- 注意：不要建 idx_memo_cards_key（card_key 已是 PRIMARY KEY）