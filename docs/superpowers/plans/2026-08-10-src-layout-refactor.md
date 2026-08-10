# VibeChatbot src-layout 重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 VibeChatbot 从扁平根目录重构为标准 src-layout 可打包结构，移除 Streamlit，统一后端组装并修复 Ink UI 启动崩溃，数据目录收拢到 `data/`。

**Architecture:** 核心代码迁入 `src/vibechatbot/` 包（config/chat/history/vector_store/agent/agents/tools），新增 `pyproject.toml` 提供 `pip install -e .` 与 `vibechat` 控制台脚本；`runtime.py` 统一组装后端单例供 CLI 与 Ink UI 共用；`ui/bridge.py` 瘦身为 shim；路径全部由 `config.py` 基于 `PROJECT_ROOT` 解析。

**Tech Stack:** Python 3.10+ / setuptools / DeepSeek(openai SDK) / Chroma / Ink(React) / Docker / unittest

**测试基线：** 重构前 `python -m unittest discover -s tests` = 58 个用例全部通过。重构后必须保持 58 个全过 + 新增 `is_simple_tool_task` 测试。

**验证命令（Windows Git Bash）：** 测试跑 `PYTHONPATH=src python -m unittest discover -s tests`

---

### Task 1: 包骨架 + pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: `src/vibechatbot/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: 创建包目录与骨架文件**

```bash
mkdir -p src/vibechatbot
```

`src/vibechatbot/__init__.py`:
```python
"""VibeChatbot: DeepSeek 驱动的终端聊天 + Agentic RAG 助手。"""

__version__ = "0.2.0"
```

`pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "vibechatbot"
version = "0.2.0"
description = "DeepSeek 驱动的终端聊天 + Agentic RAG 助手"
requires-python = ">=3.10"
dependencies = [
    "python-dotenv>=1.0",
    "openai>=1.0",
    "pypdf>=4.0",
    "chromadb>=0.5",
    "sentence-transformers>=3.0",
]

[project.scripts]
vibechat = "vibechatbot.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: 更新 .gitignore（数据目录收拢 + 打包产物）**

把 `.gitignore` 中 `CHAT/`、`TASK/`、`AGENTIC/`、`OUTPUT/`、`VECTOR_DB/`、`.hf_cache/` 这五行整块替换为：

```gitignore
# 运行时数据目录(统一收拢到 data/,挂载卷/本地数据,不入库)
data/
.hf_cache/

# Python 打包产物
build/
dist/
*.egg-info/
.pytest_cache/
```

（保留 `*.json`、`prompt/*`、`ui/node_modules/`、`ui/.build/` 等原有规则不动）

- [ ] **Step 3: 验证包可导入**

```bash
PYTHONPATH=src python -c "import vibechatbot; print(vibechatbot.__version__)"
```
Expected: `0.2.0`

- [ ] **Step 4: 跑一遍基线测试确认环境可用**

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
Expected: `Ran 58 tests ... OK`

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml src/ .gitignore
git commit -m "chore: scaffold src-layout with pyproject.toml"
```

---

### Task 2: 迁移核心服务与工具（config/history/chat/vector_store + TOOLS）

**Files:**
- Move: `config.py` `history.py` `chat.py` `vector_store.py` → `src/vibechatbot/`
- Move: `TOOLS/` → `src/vibechatbot/tools/`（`basic_tools.py` → `file_tools.py`）
- Modify: `src/vibechatbot/config.py`（PROJECT_ROOT 逻辑 + 数据目录常量）
- Modify: `src/vibechatbot/chat.py`（import 改包内）
- Modify: `src/vibechatbot/tools/__init__.py`（import 改包内）
- Modify: `src/vibechatbot/tools/file_tools.py`（import 改包内）
- Test: `tests/`（本任务后应仍全绿）

- [ ] **Step 1: git mv 移动文件**

```bash
mkdir -p src/vibechatbot
git mv config.py src/vibechatbot/config.py
git mv history.py src/vibechatbot/history.py
git mv chat.py src/vibechatbot/chat.py
git mv vector_store.py src/vibechatbot/vector_store.py
git mv TOOLS src/vibechatbot/tools
git mv src/vibechatbot/tools/basic_tools.py src/vibechatbot/tools/file_tools.py
```

- [ ] **Step 2: 重写 config.py 的路径解析（其余常量保持）**

`src/vibechatbot/config.py` 全文替换为：

```python
"""应用配置：环境变量 + 项目根/数据目录统一解析。"""

import os

from dotenv import load_dotenv

# 包目录（.../src/vibechatbot）
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_project_root(start: str) -> str:
    """从包目录向上找 pyproject.toml 所在的项目根；找不到回退 CWD。"""
    current = start
    for _ in range(5):
        if os.path.exists(os.path.join(current, "pyproject.toml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.getcwd()


# 项目根目录（可用 VIBECHAT_ROOT 环境变量显式覆盖）
PROJECT_ROOT = os.getenv("VIBECHAT_ROOT", _find_project_root(_PACKAGE_DIR))

# 加载项目根目录下的 .env（绝对路径，任意工作目录下运行都能找到）
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ---- 运行时数据目录（统一收拢到 data/）----
DATA_DIR = os.getenv("VIBECHAT_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
CHAT_DIR = os.path.join(DATA_DIR, "CHAT")
TASK_DIR = os.path.join(DATA_DIR, "TASK")
AGENTIC_DIR = os.path.join(DATA_DIR, "AGENTIC")
OUTPUT_DIR = os.path.join(DATA_DIR, "OUTPUT")
VECTOR_DB_DIR = os.path.join(DATA_DIR, "VECTOR_DB")
HISTORY_FILE = os.path.join(CHAT_DIR, "history.json")

# ---- 提示词目录 ----
PROMPT_DIR = os.path.join(PROJECT_ROOT, "prompt")
PROMPT_FILE = os.path.normpath(
    os.path.join(PROJECT_ROOT, os.getenv("PROMPT", "prompt/system"))
)

# ---- DeepSeek API ----
DEEPSEEK_API = os.getenv("DEEPSEEK_API", "").strip()
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com").strip()
MODEL_DEFAULT = os.getenv("MODEL_DEFAULT", os.getenv("MODLE_DEFAULT", "deepseek-chat")).strip()
```

- [ ] **Step 3: 更新 chat.py 的 import**

`src/vibechatbot/chat.py` 第 13-14 行改为：

```python
from vibechatbot.config import BASE_URL, DEEPSEEK_API, MODEL_DEFAULT, PROMPT_FILE
from vibechatbot.history import HISTORY_FILE, History
```

- [ ] **Step 4: 更新 tools 包 import**

`src/vibechatbot/tools/__init__.py` 第 9 行改为：

```python
from vibechatbot.tools.file_tools import TOOLS as BASIC_TOOLS
```

`src/vibechatbot/tools/file_tools.py` 第 8 行改为：

```python
from vibechatbot.vector_store import VectorStore
```

- [ ] **Step 5: 验证导入 + 全量测试**

```bash
PYTHONPATH=src python -c "from vibechatbot.chat import Chat; from vibechatbot.tools import TOOL_DEFINITIONS; print(len(TOOL_DEFINITIONS))"
```
Expected: `4`

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
Expected: `Ran 58 tests ... OK`（本任务未动 tests 依赖的 `agents.*` 与 `ui.bridge`，应保持全绿）

- [ ] **Step 6: 提交**

```bash
git add -A src/
git commit -m "refactor: move core services and tools into vibechatbot package"
```

---

### Task 3: 迁移自主任务 Agent

**Files:**
- Move: `agent.py` → `src/vibechatbot/agent.py`
- Modify: `src/vibechatbot/agent.py`（import 改包内）
- Modify: `agents/executor.py`（lazy import TOOLS 改包内，防根目录 TOOLS 消失后运行期崩）

- [ ] **Step 1: git mv + 更新 import**

```bash
git mv agent.py src/vibechatbot/agent.py
```

`src/vibechatbot/agent.py` 第 7 行改为：

```python
from vibechatbot.tools import TOOL_DEFINITIONS, execute_tool
```

`agents/executor.py` 第 43、49 行的 lazy import 改为：

```python
    from vibechatbot.tools import TOOL_DEFINITIONS
```
```python
    from vibechatbot.tools import execute_tool
```

- [ ] **Step 2: 验证 + 全量测试**

```bash
PYTHONPATH=src python -c "from vibechatbot.agent import Agent; print(Agent.__name__)"
```
Expected: `Agent`

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
Expected: `Ran 58 tests ... OK`

- [ ] **Step 3: 提交**

```bash
git add -A src/ agents/executor.py
git commit -m "refactor: move autonomous agent into vibechatbot package"
```

---

### Task 4: 迁移 agents/ 包 + 重构 bridge + 更新全部测试

**Files:**
- Move: `agents/` → `src/vibechatbot/agents/`
- Modify: `src/vibechatbot/agents/`（base 内互引改包内 + executor lazy import + 三个 prompt 默认路径改 config + pipeline 补 `is_simple_tool_task`）
- Create: `src/vibechatbot/bridge.py`（从 `ui/bridge.py` 迁移，去 sys.path 黑客）
- Modify: `ui/bridge.py`（瘦身 shim）
- Modify: `tests/`（全部 import 前缀改为 `vibechatbot.`）

- [ ] **Step 1: git mv agents/ 进包**

```bash
mkdir -p src/vibechatbot
git mv agents src/vibechatbot/agents
```

- [ ] **Step 2: 更新 agents/ 包内 import**

以下文件把 `from agents.base import AgentMessage, BaseAgent` 改为 `from vibechatbot.agents.base import AgentMessage, BaseAgent`：
- `src/vibechatbot/agents/rewriter.py:11`
- `src/vibechatbot/agents/executor.py:19`
- `src/vibechatbot/agents/verifier.py:12`
- `src/vibechatbot/agents/pipeline.py:11`

`src/vibechatbot/agents/executor.py` lazy import（第 43、49 行）改为 `from vibechatbot.tools import TOOL_DEFINITIONS` / `from vibechatbot.tools import execute_tool`。

`src/vibechatbot/agents/__init__.py` 第 3-7 行改为（原为 `from agents.base` 绝对导入，必须一并改）：

```python
from vibechatbot.agents.base import AgentMessage, BaseAgent
from vibechatbot.agents.executor import ExecutorAgent
from vibechatbot.agents.pipeline import Pipeline
from vibechatbot.agents.rewriter import RewriterAgent
from vibechatbot.agents.verifier import VerifierAgent
```
（`__all__` 列表保持不变。）

- [ ] **Step 3: 三个 prompt 默认路径改从 config 取（保证 Ink UI 任意 CWD 都能读对提示词）**

`src/vibechatbot/agents/executor.py:28`：
```python
DEFAULT_EXECUTOR_PROMPT_FILE = os.path.join("prompt", "executor")
```
改为：
```python
from vibechatbot import config

DEFAULT_EXECUTOR_PROMPT_FILE = os.path.join(config.PROMPT_DIR, "executor")
```
（`import os` 保留，因为 `_load_prompt` 还用 `os`；在文件顶部 import 区加 `from vibechatbot import config`）

`src/vibechatbot/agents/rewriter.py:13` 同理：
```python
DEFAULT_REWRITE_PROMPT_FILE = os.path.join(config.PROMPT_DIR, "rewriter")
```

`src/vibechatbot/agents/verifier.py:14` 同理：
```python
DEFAULT_VERIFIER_PROMPT_FILE = os.path.join(config.PROMPT_DIR, "verifier")
```

- [ ] **Step 4: 在 pipeline.py 补上缺失的 is_simple_tool_task**

`src/vibechatbot/agents/pipeline.py` 文件末尾追加：

```python
# 简单工具任务快速通道：不涉及知识库推理，直接由执行器完成，跳过复写/核查
_SIMPLE_TOOL_KEYWORDS = (
    "读取", "读文件", "保存", "生成", "写入", "输出",
    "load", "save_file", "add_documents", "入库",
)


def is_simple_tool_task(task: str) -> bool:
    """判断任务是否为无需检索/核查的简单工具调用（快速通道）。

    启发式：命中任意简单工具关键词即判定为 True。关键词可在此处调整。
    """
    return any(keyword in task for keyword in _SIMPLE_TOOL_KEYWORDS)
```

- [ ] **Step 5: 迁移 Bridge 类到 vibechatbot/bridge.py**

`ui/bridge.py` 全文删除，创建 `src/vibechatbot/bridge.py`，内容为原文件但：
1. 删除顶部 `_PROJECT_ROOT` sys.path 插入 + `os.chdir` 两段（第 18-23 行）
2. `from agents.base import AgentMessage`（第 25 行）→ `from vibechatbot.agents.base import AgentMessage`
3. `main()` 内（原第 183-197 行）改为从 runtime 组装：

```python
def main():
    """组装真实后端并启动桥。"""
    from vibechatbot.runtime import build_runtime

    runtime = build_runtime()
    bridge = Bridge(
        chat=runtime.chat,
        agent=runtime.agent,
        executor=runtime.executor,
        pipeline=runtime.pipeline,
        is_simple_tool_task=runtime.is_simple_tool_task,
    )
    bridge.run()
```

其余（`_LineEmitter`、`Bridge` 类、`run`/`handle`/各 `_handle_*`）原样保留。

- [ ] **Step 6: ui/bridge.py 瘦身为 shim**

`ui/bridge.py` 全文替换为：

```python
"""Ink 前端拉起的 Python 后端入口（薄壳，逻辑在 vibechatbot.bridge）。"""

import sys

try:
    from vibechatbot.bridge import main
except ImportError:
    print(
        "vibechatbot 包未安装，请先在项目根目录运行: pip install -e .",
        file=sys.stderr,
    )
    sys.exit(1)

main()
```

- [ ] **Step 7: 更新全部测试 import**

逐文件替换（保持其余代码不动）：

| 文件 | 原 | 新 |
|---|---|---|
| `tests/test_base.py:6` | `from agents.base import AgentMessage, BaseAgent` | `from vibechatbot.agents.base import AgentMessage, BaseAgent` |
| `tests/test_rewriter.py:6` | `from agents.base import AgentMessage` | `from vibechatbot.agents.base import AgentMessage` |
| `tests/test_rewriter.py:7` | `from agents.rewriter import RewriterAgent` | `from vibechatbot.agents.rewriter import RewriterAgent` |
| `tests/test_executor.py:7` | `from agents.base import AgentMessage` | `from vibechatbot.agents.base import AgentMessage` |
| `tests/test_executor.py:8` | `from agents.executor import ExecutorAgent` | `from vibechatbot.agents.executor import ExecutorAgent` |
| `tests/test_verifier.py:6` | `from agents.base import AgentMessage` | `from vibechatbot.agents.base import AgentMessage` |
| `tests/test_verifier.py:7` | `from agents.verifier import VerifierAgent` | `from vibechatbot.agents.verifier import VerifierAgent` |
| `tests/test_pipeline.py:9` | `from agents.base import AgentMessage, BaseAgent` | `from vibechatbot.agents.base import AgentMessage, BaseAgent` |
| `tests/test_pipeline.py:10` | `from agents.pipeline import Pipeline` | `from vibechatbot.agents.pipeline import Pipeline` |
| `tests/test_bridge.py:7` | `from agents.base import AgentMessage` | `from vibechatbot.agents.base import AgentMessage` |
| `tests/test_bridge.py:8` | `from ui.bridge import Bridge` | `from vibechatbot.bridge import Bridge` |

`tests/test_ui_layout.py` 不改（仍读根下 `ui/index.jsx`）。

- [ ] **Step 8: 给 is_simple_tool_task 加测试**

`tests/test_pipeline.py` 末尾追加：

```python
from vibechatbot.agents.pipeline import is_simple_tool_task


class TestIsSimpleToolTask(unittest.TestCase):
    def test_simple_tool_keywords_return_true(self):
        for task in ("读取 C:/a.pdf 并保存", "生成报告并输出到文件", "把 D:/x.docx 入库"):
            with self.subTest(task=task):
                self.assertTrue(is_simple_tool_task(task))

    def test_knowledge_reasoning_returns_false(self):
        self.assertFalse(is_simple_tool_task("基于知识库回答深海采矿的影响"))
```

- [ ] **Step 9: 全量测试（关键验收点）**

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
Expected: `Ran 59 tests ... OK`

- [ ] **Step 10: 提交**

```bash
git add -A src/ ui/bridge.py tests/
git commit -m "refactor: move agents package and bridge into vibechatbot; fix bridge startup crash"
```

---

### Task 5: runtime.py + cli.py（替代 main.py），移除 Streamlit

**Files:**
- Create: `src/vibechatbot/runtime.py`
- Create: `src/vibechatbot/cli.py`（由 `main.py` 迁移）
- Delete: `main.py` `app.py`
- Modify: `requirements.txt`（去 streamlit）

- [ ] **Step 1: 创建 runtime.py**

`src/vibechatbot/runtime.py`:

```python
"""后端单例统一组装：CLI 与 Ink UI 共用同一套 chat/agent/agentic 后端。"""

from vibechatbot.agent import Agent
from vibechatbot.agents import ExecutorAgent, Pipeline, RewriterAgent, VerifierAgent
from vibechatbot.agents.pipeline import is_simple_tool_task
from vibechatbot.chat import Chat


class Runtime:
    """CLI / Ink UI 共用的后端组件集合。"""

    def __init__(self, chat, agent, executor, pipeline, is_simple_tool_task):
        self.chat = chat
        self.agent = agent
        self.executor = executor
        self.pipeline = pipeline
        self.is_simple_tool_task = is_simple_tool_task


def build_runtime() -> Runtime:
    """构造聊天客户端、自主 Agent 与 Agentic RAG 流水线单例。"""
    chat_client = Chat()
    agent_client = Agent(chat_client)
    agentic_verifier = VerifierAgent(chat=chat_client)
    agentic_executor = ExecutorAgent(chat=chat_client)
    agentic_pipeline = Pipeline(
        [
            RewriterAgent(chat=chat_client),
            agentic_executor,
            agentic_verifier,
        ],
        verifier=agentic_verifier,
        max_retries=3,
    )
    return Runtime(
        chat=chat_client,
        agent=agent_client,
        executor=agentic_executor,
        pipeline=agentic_pipeline,
        is_simple_tool_task=is_simple_tool_task,
    )
```

- [ ] **Step 2: 创建 cli.py（原 main.py 迁移）**

`src/vibechatbot/cli.py`：内容复制自 `main.py`，改 3 处：
1. 把原第 5-23 行（`from agent import Agent` 到 `agentic_pipeline = Pipeline(...)` 整段 import + 单例拼装）整体替换为：

```python
import asyncio

from vibechatbot import config
from vibechatbot.runtime import build_runtime

runtime = build_runtime()
chat_client = runtime.chat
agent_client = runtime.agent
agentic_pipeline = runtime.pipeline
```
2. （已在上一步整段替换完成，无需单独删除。）
3. `show_help()` 的路径说明改为从 config 取：

```python
    print(f"聊天记录 -> {config.CHAT_DIR}，任务记录 -> {config.TASK_DIR}，流水线记录 -> {config.AGENTIC_DIR}")
```

其余（`show_help` 命令列表、`agent_loop`、`agentic_loop`、`chat_loop`、`main`）原样保留。`agentic_loop` 里用到的 `agentic_pipeline.run(...)`、`agentic_pipeline.attempts` 指向 `runtime.pipeline`，行为不变。

- [ ] **Step 3: 删除 main.py / app.py，requirements 去 streamlit**

```bash
git rm main.py app.py
```

`requirements.txt` 删除 `streamlit>=1.30` 一行，保留其余 5 个依赖（与 pyproject 一致）。

- [ ] **Step 4: 验证 CLI 可启动**

```bash
printf '/exit\n' | PYTHONPATH=src python -m vibechatbot.cli
```
Expected: 打印引导语（含 `/chat /agent /agentic` 与 data/ 路径说明），输入 `/exit` 后打印 `再见！` 退出。无 Traceback。

- [ ] **Step 5: 全量测试 + 提交**

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
Expected: `Ran 59 tests ... OK`

```bash
git add -A src/ requirements.txt
git commit -m "refactor: add runtime factory and cli entry; remove streamlit app"
```

---

### Task 6: 数据目录收拢到 data/ + 模块改用 config 路径

**Files:**
- Modify: `src/vibechatbot/history.py`（HISTORY_FILE 从 config 取）
- Modify: `src/vibechatbot/chat.py`（HISTORY_FILE import 从 config 取）
- Modify: `src/vibechatbot/agent.py`（TASK_DIR 从 config 取）
- Modify: `src/vibechatbot/agents/pipeline.py`（archive_dir 默认从 config 取）
- Modify: `src/vibechatbot/tools/file_tools.py`（OUTPUT_DIR 从 config 取）
- Modify: `src/vibechatbot/vector_store.py`（DB_DIR 从 config 取）
- Data: 迁移根目录运行时数据 → `data/`

- [ ] **Step 1: 迁移现有数据文件**

```bash
mkdir -p data/CHAT data/TASK data/AGENTIC data/OUTPUT data/VECTOR_DB
# 已存在的运行时数据迁移（不存在则跳过）
[ -f CHAT/history.json ] && mv CHAT/history.json data/CHAT/history.json
[ -d OUTPUT ] && mv OUTPUT/* data/OUTPUT/ 2>/dev/null || true
[ -d AGENTIC ] && mv AGENTIC/*.json data/AGENTIC/ 2>/dev/null || true
[ -d VECTOR_DB ] && mv VECTOR_DB/* data/VECTOR_DB/ 2>/dev/null || true
# 清理旧目录
rm -rf CHAT TASK OUTPUT AGENTIC VECTOR_DB
```
（这些目录已被 gitignore，纯磁盘移动，不入库。）

- [ ] **Step 2: history.py 从 config 取 HISTORY_FILE**

`src/vibechatbot/history.py`：
- 第 6 行 `HISTORY_FILE = os.path.join("CHAT", "history.json")` 改为：

```python
from vibechatbot.config import HISTORY_FILE
```
（`import os` 若只被 HISTORY_FILE 使用则一并删除；`load/save/clear/compress` 里 `os.path.exists`、`os.makedirs` 仍用到 `os`，保留 `import os`。）

- [ ] **Step 3: chat.py 的 HISTORY_FILE 改从 config 取**

`src/vibechatbot/chat.py` 第 13-14 行改为：

```python
from vibechatbot.config import BASE_URL, DEEPSEEK_API, HISTORY_FILE, MODEL_DEFAULT, PROMPT_FILE
from vibechatbot.history import History
```

- [ ] **Step 4: agent.py 的 TASK_DIR 从 config 取**

`src/vibechatbot/agent.py` 第 11 行：

```python
TASK_DIR = "TASK"
```
改为：

```python
from vibechatbot import config

TASK_DIR = config.TASK_DIR
```

- [ ] **Step 5: pipeline.py 的 archive_dir 从 config 取**

`src/vibechatbot/agents/pipeline.py` 第 20 行 `archive_dir: str = "AGENTIC"` 改为 `archive_dir: str = config.AGENTIC_DIR`，并在文件顶部加 `from vibechatbot import config`。

- [ ] **Step 6: file_tools.py 的 OUTPUT_DIR 从 config 取**

`src/vibechatbot/tools/file_tools.py` 第 20 行 `OUTPUT_DIR = "OUTPUT"` 改为：

```python
from vibechatbot import config

OUTPUT_DIR = config.OUTPUT_DIR
```

- [ ] **Step 7: vector_store.py 的 DB_DIR 从 config 取**

`src/vibechatbot/vector_store.py` 第 8 行 `DB_DIR = "VECTOR_DB"` 改为：

```python
from vibechatbot import config

DB_DIR = config.VECTOR_DB_DIR
```

- [ ] **Step 8: 验证路径解析 + 全量测试**

```bash
PYTHONPATH=src python -c "from vibechatbot import config; print(config.CHAT_DIR); print(config.PROJECT_ROOT)"
```
Expected: 输出 `...\data\CHAT` 与项目根绝对路径

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
Expected: `Ran 59 tests ... OK`

- [ ] **Step 9: 提交**

```bash
git add -A src/
git commit -m "refactor: consolidate runtime data under data/ via config paths"
```

---

### Task 7: Docker 更新

**Files:**
- Modify: `Dockerfile`
- Modify: `.dockerignore`
- Modify: `requirements.txt`（已在 Task 5 完成，确认）

- [ ] **Step 1: 更新 .dockerignore**

`.dockerignore` 中第 4-9 行整块：

```
# 运行数据: 挂载卷持久化,不需要打包进镜像
CHAT
TASK
OUTPUT
VECTOR_DB
.hf_cache
```
替换为：

```
# 运行数据: 挂载卷持久化,不需要打包进镜像
data
.hf_cache

# Node / Ink UI (Docker 只跑 CLI,不打包 UI 依赖)
ui/node_modules
ui/.build
```

- [ ] **Step 2: 更新 Dockerfile**

`Dockerfile` 全文替换为：

```dockerfile
# ================= VibeChatbot 容器镜像 =================
# 构建:
#   docker build -t vibechatbot .
#
# 运行终端聊天 (交互式):
#   docker run -it --rm --env-file .env -v vibe_db:/app/data/VECTOR_DB \
#     vibechatbot
#
# 数据卷: 聊天记录 / 任务记录 / 流水线 / 输出 / 向量库 统一挂到 /app/data 下
# ========================================================

# 3.12-slim: chromadb / sentence-transformers / torch 在 3.14 上支持不稳定
FROM python:3.12-slim

# PYTHONUNBUFFERED: 日志实时输出; HF_HOME: 嵌入模型缓存目录(挂载卷持久化)
# PYTHONPATH: src-layout 包位置,`python -m vibechatbot.cli` 无需安装即可运行
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    HF_HOME=/app/.hf_cache

WORKDIR /app

# 先装 torch CPU 版(~200MB),避免 PyPI 默认 CUDA 版(2GB+)导致镜像过大
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

# 预下载中文嵌入模型(bge-small-zh-v1.5),失败不阻塞构建
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" \
    || echo "警告: 嵌入模型下载失败,首次运行向量库时会自动下载"

# 复制项目代码(.env / data 已被 .dockerignore 排除)
COPY . .

# 数据持久化目录: 聊天/任务/流水线/输出/向量库 + 模型缓存
VOLUME ["/app/data", "/app/.hf_cache"]

# 默认启动终端聊天 CLI;`docker run -it` 交互使用
CMD ["python", "-m", "vibechatbot.cli"]
```

- [ ] **Step 3: 确认 requirements.txt 无 streamlit**

```bash
grep -c streamlit requirements.txt
```
Expected: 输出 `0`（已无 streamlit）

- [ ] **Step 4: 提交**

```bash
git add Dockerfile .dockerignore
git commit -m "build: update docker for src-layout cli"
```

---

### Task 8: 清理 + 最终验证

**Files:**
- Delete: 残留 `__pycache__` / 陈旧编译测试
- Create: `README.md`（简版）
- Verify: 全量测试 / CLI / bridge / 目录结构

- [ ] **Step 1: 删除全部 __pycache__ 与陈旧编译产物**

```bash
find . -type d -name __pycache__ -not -path './ui/node_modules/*' -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -not -path './ui/node_modules/*' -delete
```

- [ ] **Step 2: 新增简版 README.md**

`README.md`（根目录）写入：

```markdown
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
```

- [ ] **Step 3: 全量测试**

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
Expected: `Ran 59 tests ... OK`

- [ ] **Step 4: CLI 冒烟**

```bash
printf '/exit\n' | PYTHONPATH=src python -m vibechatbot.cli
```
Expected: 引导语 + `再见！`，无 Traceback

- [ ] **Step 5: bridge 后端冒烟（Ink UI 依赖）**

```bash
printf '{"type":"ping"}\n{"type":"exit"}\n' | PYTHONPATH=src python ui/bridge.py
```
Expected: stdout 含 `{"type":"ready"}` 与 `{"type":"pong"}`，正常退出

- [ ] **Step 6: 目录结构核对**

```bash
ls -1
```
Expected 根目录：`data/  docs/  prompt/  src/  tests/  ui/` + `pyproject.toml requirements.txt Dockerfile .env .env.example .gitignore .dockerignore README.md`
（无散落 `*.py`、无 `app.py`、无 `main.py`、无 `TOOLS/`、无 `agents/`）

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "chore: clean caches and add README for src-layout"
```

---

## 自评结果

- **Spec 覆盖**：目标结构（Task 1-6）、Streamlit 移除（Task 5）、路径集中（Task 2+6）、runtime/bridge bug 修复（Task 4+5）、Docker（Task 7）、测试更新（Task 4）、清理（Task 8）均一一对应。
- **占位符**：无 TBD/TODO；每个改动点都有完整代码或精确行号。
- **类型一致**：`build_runtime()` 返回的 `Runtime` 成员（chat/agent/executor/pipeline/is_simple_tool_task）在 cli.py 与 vibechatbot/bridge.py 中用法一致；`is_simple_tool_task` 在 pipeline.py 定义、bridge.py 与 runtime.py 导入同一符号。
