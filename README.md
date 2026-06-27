# Diary System

这是一个已经收缩到“核心链路优先”的本地日记系统。

当前只保留 5 类能力：

1. 文本日记保存、读取、编辑、删除
2. 异步 block 分析与 entry rollup
3. SQLite FTS 检索
4. 基于日记内容的聊天问答
5. 最小仪表盘概览

已移除的非核心能力：

- 云同步与 contract 回写
- 事件流同步实验
- legacy `DiaryPersonaBot`
- 本地训练 / 评测 / 数据导出
- 语音克隆 / TTS
- 复杂人格画像大盘
- 桌面打包入口

## 目录

- `server.py`：FastAPI 服务入口
- `api/`：HTTP 路由
- `storage/`：SQLite 连接与仓储
- `pipeline/`：切块、分析辅助、上下文组装
- `bot/`：聊天主链路
- `scripts/run_block_jobs.py`：block 分析 worker
- `frontend/`：当前前端

## 运行

推荐开发环境是 `.venv`：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pip --version
scripts/validate.sh
```

旧的本地虚拟环境已不再作为推荐环境。

## 验证

标准验证入口是：

```bash
scripts/validate.sh
```

这个脚本固定使用项目 `.venv`，并设置仓库根目录为 `PYTHONPATH`，避免系统或 Anaconda 的
`pytest` 抢先运行。不要在这个仓库里直接裸跑 `pytest -q`。

如果需要模拟全局 pre-push hook 的 plain `pytest -q` 形式，请显式使用项目环境：

```bash
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. pytest -q
```

第一次运行音频相关测试时，原生可选依赖可能会有冷启动延迟；这不代表测试被跳过或削弱。

```bash
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

另开一个终端运行分析 worker。当前固定的开发启动方式是：

```bash
.venv/bin/python scripts/run_block_jobs.py \
  --backend cloud \
  --preferred-provider deepseek \
  --retry-failed \
  --force \
  --loop \
  --poll-seconds 5
```

如果你只想看队列状态：

```bash
.venv/bin/python scripts/run_block_jobs.py --stats
```

## 核心 API

- `POST /api/diary/save`
- `GET /api/diary/list`
- `GET /api/diary/entry`
- `PUT /api/diary/entry`
- `DELETE /api/diary/entry`
- `POST /api/diary/entry/reanalyze`
- `POST /api/chat`
- `POST /api/voice/chat`
- `GET /api/dashboard/overview`
- `GET /health`

## 当前约束

- 语音对话仍保留 STT -> Chat，但不再返回 TTS 音频
- 仪表盘只返回最小概览，不再输出复杂画像卡片
- 分析链路默认云优先，但 API 现在只负责入队；需要有独立 worker 在跑
- 仓库里可能仍有旧表结构和旧模块痕迹，后续会继续清理

## 最小排查

- 服务起不来先看端口占用：
  `lsof -nP -iTCP:8000 -sTCP:LISTEN`
- worker 不消费先看是否忘了 `--force`，或当前机器不 idle
- 新请求一直停在 `pending`，通常是 worker 没启动
- 先查：
  `GET /api/diary/analyze_status`
  和
  `.venv/bin/python scripts/run_block_jobs.py --stats`

更完整的运行和故障说明见 [docs/operations.md](/Users/lincma/Documents/diary%20system/docs/operations.md)。
