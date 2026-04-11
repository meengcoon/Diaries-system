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

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 server.py
```

另开一个终端运行分析 worker：

```bash
python3 scripts/run_block_jobs.py --force --limit 20 --backend cloud --preferred-provider deepseek
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
- 分析链路默认云优先，云失败后才回退本地
- 仓库里可能仍有旧表结构和旧模块痕迹，后续会继续清理
