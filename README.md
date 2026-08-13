# VibeChatbot

DeepSeek 驱动的终端 Agentic RAG 助手：把聊天、任务、Agent 三种模式统一为「任务模式」，复杂任务自动走 **复写器 → 执行器 → 核查器** 闭环，简单工具任务走快速通道直达工具。

## 功能特性

- **统一任务模式**：输入任务后自动路由——简单工具任务（读取、保存、写入、入库等）走快速通道；其余任务进入 Agentic RAG 闭环。
- **三 Agent 闭环**：复写器改写任务 → 执行器检索向量库、调用工具并生成结论 → 核查器核对结论，不通过则打回。
- **打回重试机制**：核查器区分「重写」与「重搜」，分别计数，最多 3 轮重试，超限后强制输出结论并提示。
- **流式输出**：仅最终结论走流式（执行器阶段），复写/核查阶段不流式；重试时跳过已发送前缀，避免 UI 重复片段。
- **会话存档**：每个终端会话一个 JSON 文件，存放在 `data/TASK`（快速通道）或 `data/AGENTIC`（Agentic 闭环），工具调用过程也完整记录在 JSON 中，终端只输出最终结果与关键日志。
- **语义检索**：Chroma 向量库 + `bge-small-zh-v1.5` embedding，支持入库、检索、按需清理。
- **Ink 终端 UI**：`ui/` 提供 React/Ink 前端，通过 stdio JSON 协议与 Python 桥接。

## 安装

要求 Python >= 3.10。

```bash
# 方式一：以可编辑方式安装（推荐，同时获得 vibechat 命令）
pip install -e .

# 方式二：只装依赖
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为项目根目录下的 `.env` 并填写：

```bash
DEEPSEEK_API=sk-your-key-here
BASE_URL=https://api.deepseek.com
MODEL_DEFAULT=deepseek-chat
PROMPT=prompt/system
```

> 注意：`.env` 必须是**无 BOM 的 UTF-8** 编码；程序会自动从项目根目录加载，任意工作目录下运行都能找到。

### 环境变量一览

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API` | 空 | DeepSeek API Key（必填） |
| `BASE_URL` | `https://api.deepseek.com` | API 地址，可切换其他 OpenAI 兼容服务 |
| `MODEL_DEFAULT` | `deepseek-chat` | 默认模型名 |
| `PROMPT` | `prompt/system` | 系统提示词文件路径（相对项目根） |
| `VIBECHAT_ROOT` | 自动探测（pyproject.toml 所在目录） | 项目根目录覆盖 |
| `VIBECHAT_DATA_DIR` | `data/` | 运行时数据根目录 |
| `CHAT_DIR` / `TASK_DIR` / `AGENTIC_DIR` / `OUTPUT_DIR` / `VECTOR_DB_DIR` | 均在 `data/` 下 | 各数据目录（由 `VIBECHAT_DATA_DIR` 派生） |
| `HISTORY_FILE` | `data/CHAT/history.json` | 历史记录文件 |

## 运行

### CLI

```bash
vibechat
# 或 python -m vibechatbot.cli
```

可用命令：

| 命令 | 作用 |
| --- | --- |
| `/clear_history` | 清空历史记录文件 |
| `/clear_memory` | 清除当前对话记忆（messages 重置，不清 JSON） |
| `/exit` | 退出任务模式 |

任务记录写入 `data/TASK`，流水线记录写入 `data/AGENTIC`。

### Ink UI

```bash
cd ui
npm install
npm start
```

UI 通过 `ui/bridge.py`（stdio JSON 协议）与 Python 后端通信，界面右上角显示当前模型名。

## 工具列表

| 工具 | 作用 |
| --- | --- |
| `load` | 读取 word/txt/pdf 文件，转成纯文本；内置按 `\n` → `!`/`.` → 字数兜底的分块（每块约 500 字） |
| `query_documents` | 向量库语义检索 |
| `add_documents` | 将文本块入库（Chroma 向量库） |
| `save_file` | 将内容保存到 `data/OUTPUT` 白名单目录 |
| `write_file` | 修改/生成文件，白名单为**除向量库目录（`VECTOR_DB`）外的任意路径**，防止污染向量库 |

## 测试

```powershell
# Python 测试（84 个）
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests

# UI 测试
cd ui
npm run build
npm test
```

## 目录结构

```
VibeChatbot/
├── src/vibechatbot/
│   ├── config.py          # 环境变量、项目根、数据目录统一解析
│   ├── cli.py             # 统一任务模式入口
│   ├── chat.py            # 对话客户端（流式、历史、记忆）
│   ├── history.py         # 历史记录 JSON 存取、轮次压缩
│   ├── runtime.py         # 运行时可调用对象、快速通道路由
│   ├── vector_store.py    # Chroma 向量库封装
│   ├── bridge.py          # UI 桥接（stdio JSON 协议）
│   ├── agent.py           # 快速通道 agent（简单工具任务）
│   ├── agents/            # Agentic RAG 三 agent
│       ├── base.py        # 异步 Agent 基类（_call_llm、工具执行、收敛判定）
│       ├── rewriter.py    # 复写器
│       ├── executor.py    # 执行器（流式输出）
│       ├── verifier.py    # 核查器（打回：重写/重搜）
│       └── pipeline.py    # 流水线编排与重试循环
│   └── tools/
│       ├── file_tools.py  # load / save_file / write_file / 向量库工具
│       └── __init__.py    # 工具注册表（schema + 可调用对象分离）
├── prompt/                # system / rewriter / executor / verifier 提示词
├── data/                  # CHAT / TASK / AGENTIC / OUTPUT / VECTOR_DB
├── ui/                    # Ink 前端（index.jsx / workbench.jsx / layout.mjs）
├── tests/                 # Python 与 UI 测试
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## Docker（待完善）

项目尚未完成 Docker 化，`Dockerfile` 为占位实现，待项目完工后再完善。
