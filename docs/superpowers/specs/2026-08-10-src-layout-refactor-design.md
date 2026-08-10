# VibeChatbot src-layout 重构设计

日期：2026-08-10
状态：已确认

## 背景

VibeChatbot 是一个基于 DeepSeek 的终端聊天 + Agentic RAG 助手。当前代码根目录过于扁平：7 个 Python 模块混在根目录，`TOOLS/` 全大写命名不符合惯例，`agent.py`（模块）与 `agents/`（包）易混淆，`ui/bridge.py` 通过 `sys.path` 插入 + `os.chdir` 才能运行，且 `bridge.py` 引用了两个不存在的符号（`main.agentic_executor`、`pipeline.is_simple_tool_task`），导致 Ink UI 后端启动即崩溃。

目标：整理为标准 Python 包结构（src-layout + pyproject.toml，方便打包部署）、分层清晰、整体整洁。Streamlit Web UI 已被用户确认**移除**。

必须保持可用的入口：**终端 CLI**、**Ink UI**、**Docker**。

## 目标结构

```
VibeChatbot/
├── src/vibechatbot/                # 核心包（pip 可安装）
│   ├── __init__.py                 # 版本号
│   ├── config.py                   # 环境变量 + 项目根/数据目录统一解析
│   ├── chat.py                     # DeepSeek 客户端
│   ├── history.py                  # 历史持久化
│   ├── vector_store.py             # Chroma 向量库
│   ├── agent.py                    # 自主任务 Agent
│   ├── agents/                     # Agentic RAG（base/rewriter/executor/verifier/pipeline）
│   ├── tools/                      # 原 TOOLS/（改名），注册表 + 文件工具
│   ├── runtime.py                  # 新增：统一组装各单例
│   ├── cli.py                      # 原 main.py 终端入口
│   └── bridge.py                   # 原 ui/bridge.py 的 Bridge 类 + main()
├── ui/
│   ├── index.jsx / package.json / devtools-stub.js
│   └── bridge.py                   # 瘦身为 shim：from vibechatbot.bridge import main; main()
├── prompt/                         # 提示词（保持根级，便于编辑）
├── tests/                          # 更新 import 路径
├── data/                           # 运行时数据统一收拢
│   ├── CHAT/  TASK/  AGENTIC/  OUTPUT/  VECTOR_DB/
├── docs/
├── pyproject.toml                  # 新增
├── requirements.txt                # 去掉 streamlit
├── Dockerfile                      # 更新路径
└── .env / .gitignore / .dockerignore
```

## 改动清单

### 1. 代码迁移（纯移动 + import 改写，逻辑不动）

- `main.py` → `src/vibechatbot/cli.py`
- `agent.py` / `chat.py` / `history.py` / `config.py` / `vector_store.py` → `src/vibechatbot/`
- `agents/` → `src/vibechatbot/agents/`，包内 import 改为 `from vibechatbot.agents.base import ...` 形式
- `TOOLS/` → `src/vibechatbot/tools/`（`basic_tools.py` → `file_tools.py`）
- `app.py`（Streamlit）删除，`requirements.txt` 移除 streamlit

### 2. 路径统一解析

- `config.py` 新增 `PROJECT_ROOT`：从包目录向上找 `pyproject.toml`；支持环境变量 `VIBECHAT_ROOT` 覆盖；找不到时回退 `os.getcwd()`
- 在 `PROJECT_ROOT` 基础上派生统一路径常量，供各模块引用：
  - `DATA_DIR` → `CHAT_DIR` / `TASK_DIR` / `AGENTIC_DIR` / `OUTPUT_DIR` / `VECTOR_DB_DIR`
  - `HISTORY_FILE`（原在 history.py）
  - `PROMPT_DIR` / `PROMPT_FILE`
- 各模块删除硬编码相对路径（`TASK_DIR`、`archive_dir="AGENTIC"`、`OUTPUT_DIR="OUTPUT"`、`DB_DIR="VECTOR_DB"`、`os.path.join("prompt", ...)`），改从 `config` 导入
- `config.py` 保持独立（不被包内模块反向依赖），避免循环导入

### 3. runtime.py（统一后端组装 + 修复 bridge bug）

```python
# vibechatbot/runtime.py
def build_runtime() -> Runtime:
    chat = Chat()
    agent = Agent(chat)
    verifier = VerifierAgent(chat=chat)
    executor = ExecutorAgent(chat=chat)
    pipeline = Pipeline(
        [RewriterAgent(chat=chat), executor, verifier],
        verifier=verifier, max_retries=3,
    )
    return Runtime(chat, agent, executor, pipeline, is_simple_tool_task)
```

- `Runtime` 承载 `chat / agent / executor / pipeline / is_simple_tool_task` 五个成员
- CLI（`cli.py`）与 Ink 后端（`bridge.py`）都从 `build_runtime()` 取单例，消除 `main.py` 顶层散拼与 `bridge.py` 引用不存在的 `agentic_executor` 的崩溃

### 4. is_simple_tool_task（补齐缺失符号）

在 `agents/pipeline.py` 中新增：

```python
def is_simple_tool_task(task: str) -> bool:
    """判断任务是否为无需检索/核查的简单工具调用（快速通道）。"""
```

默认实现：基于关键词启发式（读文件 / 存文件 / 入库这类不依赖知识库推理的任务返回 True）。具体关键词列表实现时确定并注释说明，用户后续可调整。

### 5. pyproject.toml + 入口

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "vibechatbot"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = [python-dotenv, openai, pypdf, chromadb, sentence-transformers]

[project.scripts]
vibechat = "vibechatbot.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

- `requirements.txt` 保留（Docker 用，去掉 streamlit），依赖与 pyproject 保持一致（重复是刻意的，显式且简单）
- 开发流程：`pip install -e .` → 命令行 `vibechat` / `python -m vibechatbot.cli`

### 6. ui/bridge.py shim

```python
try:
    from vibechatbot.bridge import main
except ImportError:
    print("vibechatbot 包未安装，请先运行: pip install -e .", file=sys.stderr)
    sys.exit(1)
main()
```

- 保留在 `ui/` 下，`ui/index.jsx` 按老路径 `python bridge.py` 拉后端不受影响
- `index.jsx` / `package.json` 不改动

### 7. Docker

- 移除 streamlit 相关（env、CMD）
- `ENV PYTHONPATH=/app/src`
- `CMD ["python", "-m", "vibechatbot.cli"]`
- 数据卷挂载路径改为 `/app/data/CHAT` 等
- 注释里更新运行说明

### 8. 测试更新

- 各测试 import 改为 `vibechatbot.*` 前缀：
  - `from agents.base import ...` → `from vibechatbot.agents.base import ...`（含 pipeline / executor / rewriter / verifier）
  - `from ui.bridge import Bridge` → `from vibechatbot.bridge import Bridge`
- `tests/test_ui_layout.py` 读取 `ui/index.jsx` 的路径逻辑不变（`tests/` 仍在根下）
- 运行方式：`pip install -e .` 后 `python -m unittest discover -s tests`
- 验收：58 个测试全部通过（与基线一致）

### 9. 清理

- 删除残留 `__pycache__`（含 5 个源码已删除的陈旧编译测试：test_load_folder / test_load_pdf / test_parse_pdf / test_tool_log / test_web_pdf）
- 更新 `.gitignore`：`data/` 替代散落的 `CHAT/`、`TASK/`、`AGENTIC/`、`OUTPUT/`、`VECTOR_DB/`；保留 `*.json`、`prompt/*` 规则
- 更新 `.dockerignore`：
  - 运行时目录改为 `data`（替代 `CHAT`/`TASK`/`OUTPUT`/`VECTOR_DB`，并补上 `AGENTIC`）
  - 新增 `ui/node_modules`、`ui/.build`（Docker 只跑 CLI，不打包 UI 依赖）
  - 注意 `*.json` 规则会排除 `ui/package.json`——对 Docker 无影响（不跑 UI），保持现状即可
- 迁移现有数据文件：`CHAT/history.json`、`OUTPUT/深海采矿四主体比较分析.md` → `data/` 对应位置（VECTOR_DB 若存在一并迁移）
- 清理后根目录结构对照文档开头的「目标结构」逐项核对

## 验收标准

1. `python -m unittest discover -s tests` → 58 个用例全部通过
2. `python -m vibechatbot.cli` 能进入命令行循环（/chat /agent /agentic 可用）
3. Ink UI：`cd ui && npm start` 能拉起后端并对话（修复 agentic_executor / is_simple_tool_task 崩溃）
4. `docker build` 成功，`docker run -it ... python -m vibechatbot.cli` 可交互
5. 根目录无散落的数据目录（已收拢到 `data/`）

## 非目标

- 不改变任何业务逻辑（聊天、RAG、工具行为）
- 不引入 pytest / pytest-asyncio（沿用 unittest）
- 不迁移 prompt 文件进包（保持根级便于编辑）
