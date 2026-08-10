# VibeChatbot

基于 DeepSeek 的终端聊天 + Agentic RAG 助手。支持 `/chat` 对话、`/agent` 自主任务、
`/agentic` 复写→执行→核查闭环，以及 `ui/` 下的 Ink 终端 UI。

## 安装与运行

```bash
# 开发安装（src-layout 需要这一步才能 import vibechatbot）
pip install -e .

# 终端 CLI
vibechat            # 或 python -m vibechatbot.cli

# Ink 终端 UI（需 Node）
cd ui && npm install && npm start
```

## 目录结构

- `src/vibechatbot/` — 核心包（config/chat/history/vector_store/agent/agents/tools/runtime/cli/bridge）
- `ui/` — Ink 终端 UI + `bridge.py` 后端入口（shim）
- `prompt/` — 提示词文件
- `data/` — 运行时数据（CHAT/TASK/AGENTIC/OUTPUT/VECTOR_DB）
- `tests/` — unittest 测试（`python -m unittest discover -s tests`）
