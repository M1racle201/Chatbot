# 通用浏览器 MCP Agent 接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将外部浏览器 MCP Server 动态接入现有异步 Executor，同时保持任务领域无关、提示词不变，并让没有 MCP 配置时的本地工具行为保持不变。

**Architecture:** 新增 MCPRegistry 管理任务级 stdio session、工具发现、OpenAI schema 转换和通用结果格式化。Runtime 只在一次 Pipeline 的 asyncio 生命周期内创建 Registry，Executor 合并本地与远程工具并按命名空间异步分发；同步快速通道不连接 MCP。路由只识别通用浏览器/网页能力关键词，不包含岗位或招聘等领域关键词。

**Tech Stack:** Python 3.10+、MCP Python SDK、asyncio、contextlib.AsyncExitStack、现有 unittest 测试体系、Firecrawl/Playwright 等可配置的外部 MCP Server。

---

## 文件结构

- Create: `src/vibechatbot/mcp_registry.py` — MCP 配置读取、任务级 session 生命周期、工具 schema、调用和结果适配。
- Create: `config/mcp.json.example` — 通用 MCP Server 配置示例，Firecrawl 只作为示例。
- Modify: `src/vibechatbot/config.py` — 增加可选 MCP 配置路径。
- Modify: `src/vibechatbot/agents/executor.py` — 合并远程 schema，区分本地同步工具和 MCP 异步工具，保留现有注入接口。
- Modify: `src/vibechatbot/runtime.py` — 在 Pipeline 任务生命周期内创建并注入 Registry，异常时关闭。
- Modify: `src/vibechatbot/agents/pipeline.py` — 让通用浏览器/网页任务不走简单工具快速通道。
- Modify: `.env.example` — 增加 MCP_CONFIG 示例。
- Modify: `README.md` — 说明通用 MCP 配置和运行前置条件。
- Create: `tests/test_mcp_registry.py` — Registry 单元测试。
- Create: `tests/test_executor_mcp.py` — Executor 远程工具合并和异步调用测试。
- Modify: `tests/test_pipeline.py` — 通用 MCP 任务路由测试。
- Modify: `tests/test_runtime.py` — Registry 生命周期注入测试。
- Do not modify: `prompt/executor`、`prompt/system`、`mcp/client.py`、`mcp/server.py`。

### Task 1: 先写 MCP Registry 失败测试

**Files:**
- Create: `C:\Users\21776\Desktop\VibeChatbot\tests\test_mcp_registry.py`

- [ ] **Step 1: 写配置解析和无配置行为测试**

使用临时 JSON 文件和环境变量，固定以下接口：

~~~python
import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from vibechatbot.mcp_registry import MCPRegistry


class TestMCPRegistryConfig(unittest.TestCase):
    def test_missing_config_returns_empty_registry(self):
        registry = MCPRegistry.from_config("missing-mcp-config.json")
        self.assertEqual(registry.tool_definitions(), [])

    def test_config_keeps_server_command_and_resolves_env_names(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as file:
            json.dump(
                {
                    "servers": {
                        "browser": {
                            "enabled": True,
                            "command": "node",
                            "args": ["server.js"],
                            "env": ["BROWSER_TOKEN"],
                        }
                    }
                },
                file,
            )
            path = file.name
        self.addCleanup(lambda: os.unlink(path))

        with patch.dict(os.environ, {"BROWSER_TOKEN": "secret"}, clear=False):
            registry = MCPRegistry.from_config(path)

        self.assertEqual(registry.server_names(), ["browser"])
        self.assertEqual(registry.server_specs()[0].command, "node")
        self.assertEqual(registry.server_specs()[0].args, ("server.js",))
        self.assertEqual(registry.server_specs()[0].environment["BROWSER_TOKEN"], "secret")

    def test_disabled_server_is_not_started(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as file:
            json.dump(
                {"servers": {"browser": {"enabled": False, "command": "node"}}},
                file,
            )
            path = file.name
        self.addCleanup(lambda: os.unlink(path))

        registry = MCPRegistry.from_config(path)
        self.assertEqual(registry.server_names(), [])
~~~

- [ ] **Step 2: 写工具发现、命名空间和结果格式化失败测试**

~~~python
class FakeSession:
    def __init__(self, result=None):
        self.result = result
        self.calls = []
        self.initialized = False

    async def initialize(self):
        self.initialized = True

    async def list_tools(self):
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="search",
                    description="Search the web",
                    inputSchema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                )
            ]
        )

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.result


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class TestMCPRegistryCalls(unittest.TestCase):
    def test_discovers_namespaced_tool_and_calls_original_name(self):
        session = FakeSession(
            SimpleNamespace(content=[SimpleNamespace(text='{"items": []}')])
        )
        registry = MCPRegistry.from_server_specs(
            [{"name": "browser", "command": "node", "args": []}]
        )

        with patch(
            "vibechatbot.mcp_registry.stdio_client",
            return_value=AsyncContext(("read", "write")),
        ), patch(
            "vibechatbot.mcp_registry.ClientSession",
            return_value=AsyncContext(session),
        ):
            async def scenario():
                async with registry:
                    definitions = registry.tool_definitions()
                    result = await registry.call(
                        "browser__search", {"query": "python"}
                    )
                    return definitions, result

            definitions, result = asyncio.run(scenario())

        self.assertEqual(
            definitions[0]["function"]["name"],
            "browser__search",
        )
        self.assertEqual(session.calls, [("search", {"query": "python"})])
        self.assertEqual(result, '{"items": []}')

    def test_formats_structured_and_error_results_without_tool_branches(self):
        structured = SimpleNamespace(
            content=[SimpleNamespace(text="fallback")],
            structuredContent={"items": [{"url": "https://example.com"}]},
        )
        error = SimpleNamespace(
            content=[SimpleNamespace(text="blocked")],
            isError=True,
        )
        self.assertIn(
            '"items"',
            MCPRegistry.format_result(structured),
        )
        self.assertIn(
            '"error"',
            MCPRegistry.format_result(error),
        )

    def test_unknown_tool_returns_json_error(self):
        registry = MCPRegistry.from_server_specs([])
        result = asyncio.run(registry.call("browser__missing", {}))
        self.assertIn("未知 MCP 工具", result)
~~~

- [ ] **Step 3: 写启动失败清理测试**

使用一个成功 session 和一个会在 initialize 时抛异常的 session，断言 Registry 在第二个 server 失败时调用 AsyncExitStack.aclose，并向上抛出包含 server 名称的 MCPRegistryError。测试不启动真实 node/npx 进程。

- [ ] **Step 4: 运行 Registry 测试确认 RED**

Run:

~~~powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_mcp_registry.py' -v
~~~

Expected: FAIL，失败原因应为 `vibechatbot.mcp_registry` 尚未存在或接口尚未实现，不应是测试导入路径错误。

### Task 2: 实现通用 MCP Registry

**Files:**
- Create: `C:\Users\21776\Desktop\VibeChatbot\src\vibechatbot\mcp_registry.py`

- [ ] **Step 1: 实现配置数据结构和加载**

实现 `ServerSpec`、`MCPRegistry.from_config()`、`from_server_specs()`、`server_names()`、`server_specs()`：

~~~python
@dataclass(frozen=True)
class ServerSpec:
    name: str
    command: str
    args: tuple[str, ...] = ()
    environment: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@classmethod
def from_config(cls, path: str):
    if not os.path.exists(path):
        return cls([])
    with open(path, encoding="utf-8") as file:
        payload = json.load(file)
    raw_servers = payload.get("servers", {})
    if not isinstance(raw_servers, dict):
        raise MCPConfigError("MCP 配置的 servers 必须是对象")
    specs = []
    for name, raw in raw_servers.items():
        if not isinstance(raw, dict) or raw.get("enabled", True) is False:
            continue
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            raise MCPConfigError(f"MCP server {name} 缺少 command")
        env_names = raw.get("env", [])
        environment = {
            key: os.environ[key]
            for key in env_names
            if key in os.environ
        }
        specs.append(
            ServerSpec(
                name=name,
                command=command,
                args=tuple(str(item) for item in raw.get("args", [])),
                environment=environment,
            )
        )
    return cls(specs)
~~~

`from_server_specs()` 同时接受 `ServerSpec` 实例和上述字段字典，便于测试和
宿主程序注入；字典输入统一转换为 `ServerSpec`，并拒绝空名称、重复名称或空
command。缺少配置文件返回空 Registry，配置格式错误或缺少必填字段抛出
`MCPConfigError`。

子进程环境以当前环境为基础合并配置中声明的环境变量，不能把密钥写回配置、日志或消息。

- [ ] **Step 2: 实现 AsyncExitStack session 生命周期**

实现 `start()`、`close()`、`__aenter__()`、`__aexit__()`。每个 Server 使用：

~~~python
params = StdioServerParameters(
    command=spec.command,
    args=list(spec.args),
    env={**os.environ, **spec.environment},
)
read, write = await stack.enter_async_context(stdio_client(params))
session = await stack.enter_async_context(ClientSession(read, write))
await session.initialize()
listed = await session.list_tools()
~~~

将每个工具保存为 `exposed_name -> (session, original_name)`，并在任一 server 启动失败时关闭已经进入 stack 的所有上下文，再抛出 `MCPRegistryError`，错误中包含 server 名称。

- [ ] **Step 3: 实现通用 schema、调用和结果格式化**

工具 schema 结构固定为：

~~~python
{
    "type": "function",
    "function": {
        "name": f"{server_name}__{tool.name}",
        "description": tool.description or "",
        "parameters": tool.inputSchema or {
            "type": "object",
            "properties": {},
        },
    },
}
~~~

`call()` 只根据命名空间查表，不检查具体 Server 或工具名称；MCP 错误、未知工具和异常统一输出 JSON 字符串。若有 `structuredContent`，优先输出其 JSON；否则拼接文本 content；空结果输出 `(empty result)`。

错误 JSON 的顶层字段固定为 `error`，值为面向用户的字符串；成功的结构化
结果直接 `json.dumps(..., ensure_ascii=False)`，文本 content 按出现顺序用换行
拼接。这样 Executor 不需要知道任何具体 MCP Server 或工具。

- [ ] **Step 4: 运行 Registry 测试确认 GREEN**

Run:

~~~powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_mcp_registry.py' -v
~~~

Expected: Registry 新增测试全部 PASS。

- [ ] **Step 5: 提交 Registry 单元**

~~~powershell
git add -- src/vibechatbot/mcp_registry.py tests/test_mcp_registry.py
git commit -m "feat: 增加通用 MCP Registry"
~~~

### Task 3: 先写 Executor 和路由失败测试

**Files:**
- Create: `C:\Users\21776\Desktop\VibeChatbot\tests\test_executor_mcp.py`
- Modify: `C:\Users\21776\Desktop\VibeChatbot\tests\test_pipeline.py`

- [ ] **Step 1: 写远程工具 schema 合并和异步调用测试**

新增 FakeRegistry：

~~~python
class FakeRegistry:
    def __init__(self):
        self.calls = []

    def tool_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "browser__search",
                    "description": "Search the web",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                },
            }
        ]

    def has_tool(self, name):
        return name == "browser__search"

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return '{"results": [{"title": "Example", "url": "https://example.com"}]}'
~~~

使用现有 Executor fake LLM 结构，让第一轮返回 `browser__search` tool call，第二轮返回最终文本，断言：

- LLM 第一次收到本地工具与 browser__search 两类 schema。
- Registry 的异步 `call()` 收到原始 JSON 参数。
- 第二轮消息最后一个 `role=tool` 的 content 是 Registry 返回值。
- Executor 最终返回第二轮文本。

测试构造 `ExecutorAgent` 时显式传入 fake 的本地工具和本地执行器，避免触发
chromadb 导入；远程 Registry 只通过 `set_mcp_registry()` 注入。

- [ ] **Step 2: 写通用证据抽取测试**

使用带 `results`、`title`、`url`、`content` 的任意 MCP 结果，断言证据写入 `message.context["evidence"]`，测试工具名使用 `browser__anything`，不出现 firecrawl、job 或招聘字样。

- [ ] **Step 3: 写通用 MCP 路由测试**

在 `tests/test_pipeline.py` 增加：

~~~python
def test_browser_tasks_bypass_simple_tool_route(self):
    for task in (
        "打开网页并总结内容",
        "搜索在线资料并比较结果",
        "browse this website and report findings",
    ):
        self.assertFalse(is_simple_tool_task(task))


def test_local_save_task_stays_simple(self):
    self.assertTrue(is_simple_tool_task("保存这段文本到文件"))
~~~

- [ ] **Step 4: 运行 Executor 和路由测试确认 RED**

Run:

~~~powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_executor_mcp.py' -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_pipeline.py' -v
~~~

Expected: 新增 MCP 合并/异步调用测试和通用浏览器路由测试失败，既有 Executor/Pipeline 测试保持通过。

### Task 4: 接入 Executor、Runtime 和通用路由

**Files:**
- Modify: `src/vibechatbot/agents/executor.py`
- Modify: `src/vibechatbot/runtime.py`
- Modify: `src/vibechatbot/agents/pipeline.py`

- [ ] **Step 1: 给 Executor 增加任务级 Registry 注入**

保留现有 `tools` 和 `tool_executor` 参数，增加 `mcp_registry=None` 和 `set_mcp_registry(registry)`。本地基础 schema 与当前 Registry schema 分开计算：

~~~python
def _tools_for_task(self):
    local = self.tools if self.tools is not None else _default_tools()
    remote = (
        self.mcp_registry.tool_definitions()
        if self.mcp_registry is not None
        else []
    )
    return list(local) + list(remote)
~~~

`_call_llm()`、流式调用和注入的 llm 都使用 `_tools_for_task()`，不把远程工具永久写入 `self.tools`，避免下一个任务复用已关闭 session 的 schema。

- [ ] **Step 2: 给 Executor 增加通用异步分发**

在工具循环中先判断 `mcp_registry.has_tool(name)`：

~~~python
if self.mcp_registry is not None and self.mcp_registry.has_tool(name):
    result = await self.mcp_registry.call(name, arguments)
else:
    result = await asyncio.to_thread(self.tool_executor, name, arguments)
    if inspect.isawaitable(result):
        result = await result
~~~

保留现有 tool_executor 测试注入；MCP 结果仍进入统一的 tool message、step callback 和通用 evidence 抽取。

- [ ] **Step 3: 给 Runtime 增加任务级 MCP 生命周期**

在 Runtime 保存可选的 `mcp_config_path` 和 `mcp_executor`，Pipeline 分支改为调用一个异步辅助函数。为兼容现有测试和外部调用，两个参数默认
为 `None`；没有注入 Executor 时直接沿用现有 Pipeline 路径，不创建 Registry：

~~~python
async def _run_pipeline_task(self, task, context, stream_callback, step_callback):
    if self.mcp_executor is None:
        return await self.pipeline.run(
            task,
            context=context,
            stream_callback=stream_callback,
            step_callback=step_callback,
        )
    registry = MCPRegistry.from_config(self.mcp_config_path)
    async with registry:
        self.mcp_executor.set_mcp_registry(registry)
        try:
            return await self.pipeline.run(
                task,
                context=context,
                stream_callback=stream_callback,
                step_callback=step_callback,
            )
        finally:
            self.mcp_executor.set_mcp_registry(None)
~~~

`build_runtime()` 将 `agentic_executor` 注入 Runtime。快速通道不启动 Registry。

- [ ] **Step 4: 增加配置路径和通用 MCP 路由关键词**

在 config.py 增加：

~~~python
MCP_CONFIG = os.getenv(
    "MCP_CONFIG",
    os.path.join(PROJECT_ROOT, "config", "mcp.json"),
)
~~~

在 is_simple_tool_task() 中先检查能力关键词：

~~~python
_MCP_TASK_KEYWORDS = (
    "浏览器", "网页", "网站", "搜索", "在线查询", "联网",
    "research", "browse", "web", "browser",
)


def is_simple_tool_task(task: str) -> bool:
    normalized = task.lower()
    if any(keyword in normalized for keyword in _MCP_TASK_KEYWORDS):
        return False
    return any(keyword in task for keyword in _SIMPLE_TOOL_KEYWORDS)
~~~

不加入岗位、招聘、职位等领域关键词。该判断只负责避免本地保存/读取等快速
通道吞掉浏览器任务；没有命中简单工具关键词的普通任务仍按原逻辑进入 Pipeline。

- [ ] **Step 5: 运行 Executor、Pipeline 和 Runtime 聚焦测试确认 GREEN**

Run:

~~~powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_executor_mcp.py' -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_pipeline.py' -v
& '.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_runtime.py' -v
~~~

Expected: 新增测试和既有三个测试模块全部 PASS。

- [ ] **Step 6: 提交 Agent 集成单元**

~~~powershell
git add -- src/vibechatbot/agents/executor.py src/vibechatbot/runtime.py src/vibechatbot/agents/pipeline.py src/vibechatbot/config.py tests/test_executor_mcp.py tests/test_pipeline.py tests/test_runtime.py
git commit -m "feat: 将通用 MCP 工具接入 Agent"
~~~

### Task 5: 添加配置示例和文档，保持提示词不变

**Files:**
- Create: `C:\Users\21776\Desktop\VibeChatbot\config\mcp.json.example`
- Modify: `C:\Users\21776\Desktop\VibeChatbot\.env.example`
- Modify: `C:\Users\21776\Desktop\VibeChatbot\README.md`
- Do not modify: `C:\Users\21776\Desktop\VibeChatbot\prompt\executor`
- Do not modify: `C:\Users\21776\Desktop\VibeChatbot\prompt\system`

- [ ] **Step 1: 添加通用 MCP 配置示例**

内容只包含 Firecrawl 示例，不把实现绑定到它：

~~~json
{
  "servers": {
    "firecrawl": {
      "enabled": true,
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "env": ["FIRECRAWL_API_KEY"]
    }
  }
}
~~~

- [ ] **Step 2: 添加环境变量说明**

在 .env.example 增加：

~~~text
MCP_CONFIG=config/mcp.json
FIRECRAWL_API_KEY=your-key-here
~~~

不添加真实 key，不修改任何提示词。

- [ ] **Step 3: 更新 README**

说明：

- 复制 config/mcp.json.example 为 config/mcp.json。
- 在 .env 设置 MCP_CONFIG 和 MCP Server 所需环境变量。
- MCP Server 必须是用户配置的固定命令，模型不能动态启动任意命令。
- 没有 config/mcp.json 时 Agent 仍使用本地工具。
- Firecrawl 只是示例，可替换为 Playwright 或其他 MCP Server。
- 运行前需要 Node.js/npx 和对应 MCP Server 依赖。

- [ ] **Step 4: 验证提示词没有变更**

Run:

~~~powershell
git diff -- prompt/executor prompt/system
~~~

Expected: 无输出。

- [ ] **Step 5: 提交配置和文档**

~~~powershell
git add -- config/mcp.json.example .env.example README.md
git commit -m "docs: 增加通用 MCP 配置说明"
~~~

### Task 6: 最终验证和安全边界检查

**Files:**
- Test: `tests/test_mcp_registry.py`
- Test: `tests/test_executor_mcp.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_runtime.py`
- Verify: `prompt/executor`
- Verify: `prompt/system`

- [ ] **Step 1: 运行 MCP 相关聚焦测试**

~~~powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_mcp_registry.py' -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_executor_mcp.py' -v
~~~

Expected: 全部 PASS，不要求外网和 Firecrawl API key。

- [ ] **Step 2: 运行全量回归测试**

~~~powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -v
~~~

Expected: 本次相关测试全部通过；若出现已有 Windows/Chroma 临时目录 WinError 32，只记录为环境性错误，不将其归因于 MCP 改动。

- [ ] **Step 3: 检查提示词和领域耦合**

~~~powershell
git diff -- prompt/executor prompt/system
Select-String -Path src/vibechatbot/mcp_registry.py,src/vibechatbot/agents/executor.py,src/vibechatbot/agents/pipeline.py -Pattern '岗位|招聘|职位|firecrawl__'
~~~

Expected: 第一条无输出；第二条不出现岗位、招聘、职位或 Firecrawl 专用工具分支。

- [ ] **Step 4: 检查差异边界和语法**

~~~powershell
& '.\.venv\Scripts\python.exe' -m py_compile src\vibechatbot\mcp_registry.py src\vibechatbot\agents\executor.py src\vibechatbot\runtime.py src\vibechatbot\agents\pipeline.py tests\test_mcp_registry.py tests\test_executor_mcp.py
git diff --check
git status --short --branch
~~~

Expected: 语法检查和 diff 检查通过；现有 pyproject.toml、requirements.txt、mcp/server.py 等用户改动不被覆盖。

- [ ] **Step 5: 提交最终状态**

~~~powershell
git status --short --branch
git log -4 --oneline --decorate
~~~

Expected: 实现提交、测试提交和文档提交可追溯，提示词文件没有新改动。
