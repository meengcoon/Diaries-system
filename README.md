# Diary System

Diary System 是一个「本地优先 + 云增强」的日记分析与问答系统，目标是把原始日记沉淀成可检索、可追溯、可持续更新的个人知识与记忆层。

系统强调三件事：
- 写日记时低延迟：保存接口不做重模型推理，只入库与排队。
- 分析结果可落地：所有分析、检索索引、记忆更新都写入本地 SQLite。
- 聊天可溯源：优先基于 RAG 上下文回答，证据不足时返回“未记录”。

## 系统功能（详细）

### 1) 日记采集与持久化
- `POST /api/diary/save`：
  - 先把文本追加到 `diaries/YYYY-MM-DD.txt` 作为文本备份。
  - 同步写入结构化表 `entries`。
  - 自动切块并写 `entry_blocks`。
  - 为每个块创建分析任务 `block_jobs`。
- 输入防护：
  - 空文本拒绝。
  - 超长文本拒绝（默认最大 8000 字符）。

### 2) 异步分析流水线（本地/云）
- `scripts/run_block_jobs.py` 消费 `block_jobs`：
  - 支持本地模型分析（local）。
  - 支持云端提供商分析（cloud，DeepSeek/Qwen）。
  - 自动重试、超时保护、stale running 任务复位。
- 分析产物：
  - 每个块写入 `block_analysis`（JSON、模型、版本、状态）。
  - 失败/跳过也有状态记录，便于运维排查。

### 3) Entry 级聚合（Rollup）
- 当某条 entry 的所有块达到终态（done/skipped/failed_exhausted）：
  - 聚合所有可用块分析为 `entry_analysis`。
  - 生成统一结构：`summary/signals/topics/facts/todos/...`。
  - 记录 `rollup_meta`（总块数、成功数、跳过数、失败数）。

### 4) RAG 检索层（SQLite FTS5）
- Rollup 完成后自动写入 `entry_fts`（全文检索索引）。
- 聊天检索流程：
  - 从用户问题生成检索 query。
  - Top-K 检索 `entry_fts`，必要时 fallback 到 LIKE。
  - 只回填结构化摘要字段，不回填原始 raw_text。
- 历史重建支持：
  - `scripts/rebuild_fts.py` 可重建 FTS 索引。

### 5) 长期记忆库（mem_cards）
- 记忆表：
  - `mem_cards`：当前记忆卡。
  - `mem_card_changes`：记忆变更审计。
- 触发策略：
  - Rollup 后先判定是否“有意义内容”（summary/topics/facts/todos/signals）。
  - 满足条件才尝试记忆更新，避免噪声写入。
- 更新策略：
  - 默认云优先（DeepSeek）生成更新操作。
  - 云失败时自动降级为 deterministic fallback，确保链路不断。

### 6) 聊天问答（Cascade）
- 接口：`POST /api/chat`
- 路径：
  - 路由模型决定 intent（diary_qa/general）与检索参数。
  - 构建 `context_pack`（recent + topk + mem_cards）。
  - 生成答案并约束输出 schema。
- 可靠性规则：
  - diary_qa 且证据不足时，返回“未记录”。
  - 接口有总超时和 fail-closed 保护，不会无限挂起。

### 7) 云同步与隐私网关
- 云同步接口：
  - `POST /api/diary/cloud/sync_existing`
  - `GET /api/diary/cloud/state`
- 同步机制：
  - 以文件字节偏移做增量同步（watermark）。
  - 仅在“云返回结果且本地 apply 成功”后推进 watermark。
- 隐私网关：
  - `POST /api/privacy/contract` 生成脱敏 contract。
  - 可做邮箱/电话/URL/证件号等替换与实体伪名化。
  - `POST /api/contract/apply` 把云结果合约写回本地。

### 8) 可观测性与运维
- 健康与运行态：
  - `GET /health`
  - `GET /api/_bot`
  - `GET /api/_routes`
  - `GET /api/diary/analyze_status`
- 任务控制：
  - `POST /api/diary/analyze_latest` 可后台触发回填+分析。
  - `scripts/backfill_blocks_jobs.py` 可为历史 entry 补建任务。

### 9) 本地训练能力（可选）
- 支持从 SQLite 导出 SFT 数据并训练 LoRA（见 `docs/local_training.md`）。
- 默认生产链路不依赖训练，可直接运行。

## 数据库核心表

- 输入层：`entries`, `entry_blocks`, `block_jobs`, `block_analysis`
- 检索层：`entry_analysis`, `entry_fts`（及其 FTS 附表）
- 记忆层：`mem_cards`, `mem_card_changes`
- 云同步层：`cloud_sync_state`
- 云调用审计/缓存：`llm_calls`, `llm_cache`

## 快速启动

1. 安装依赖

```bash
cd "diary system"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 配置环境变量（DeepSeek 全上云推荐）

```bash
export CLOUD_ENABLED=1
export CLOUD_DEFAULT_PROVIDER=deepseek
export DEEPSEEK_API_KEY="<your_deepseek_key>"

# 记忆更新走云端，避免本地模型负载
export MEM_UPDATE_PROVIDER=deepseek
export MEM_UPDATE_FORCE_CLOUD=1
export MEM_UPDATE_USE_LOCAL_LLM=0
```

3. 启动服务

```bash
python3 server.py
```

4. 启动分析 Worker

```bash
python3 scripts/run_block_jobs.py --force --limit 20 --backend cloud --preferred-provider deepseek
```

## 主要 API 一览

- `POST /api/diary/save`
- `GET /api/diary/list`
- `GET /api/diary/read`
- `POST /api/diary/analyze_latest`
- `GET /api/diary/analyze_status`
- `POST /api/chat`
- `POST /api/privacy/contract`
- `POST /api/contract/apply`
- `POST /api/diary/cloud/sync_existing`
- `GET /api/diary/cloud/state`
- `GET /api/_bot`
- `GET /api/_routes`
- `GET /health`

## 常用运维命令

查看队列统计：

```bash
python3 scripts/run_block_jobs.py --stats
```

补历史 blocks/jobs：

```bash
python3 scripts/backfill_blocks_jobs.py --limit 500
```

重建 FTS 索引：

```bash
python3 scripts/rebuild_fts.py --clear
```

## 端到端数据流

1. 用户保存日记 -> `entries + entry_blocks + block_jobs`
2. Worker 异步分析 block -> `block_analysis`
3. Entry 终态后 rollup -> `entry_analysis`
4. 同步更新 RAG 索引 -> `entry_fts`
5. 判定必要性后更新记忆 -> `mem_cards + mem_card_changes`
6. 聊天请求构建 `context_pack` 并生成回答

## 安全与密钥管理

- API Key 仅通过环境变量或 `.env` 提供，不要硬编码到代码。
- 本仓库建议忽略：
  - `.env`, `.env.*`
  - `.venv`, `.ven`, `venv`
  - 本地数据库与日志文件
- 若敏感文件曾被 Git 跟踪，需先执行 `git rm --cached <file>` 停止追踪。
