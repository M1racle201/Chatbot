# 通用 MCP 客户端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `mcp/client.py` 改造成通过命令行调用任意 MCP 工具的通用客户端，不再为 `add`、`echo` 等具体工具编写专用结果处理。

**Architecture:** 客户端用 `argparse` 解析 `--list`、工具名和 JSON 对象参数；用一个通用 `call_tool()` 转发工具调用；用一个通用 `format_tool_result()` 处理文本、结构化内容和未知内容块。服务端启动、初始化和通信错误统一转换为非零退出状态。

**Tech Stack:** Python 3.10+ 标准库（`argparse`、`asyncio`、`json`、`unittest`）、MCP 2.x stdio client。

---

## 文件结构

- Create: `tests/test_mcp_client.py` — 通过假 session 和假 MCP 结果测试参数解析、通用调用、结果格式化和错误状态，不启动真实服务进程。
- Modify: `mcp/client.py` — 删除 `add_result`、`echo_result` 等硬编码调用，增加命令行解析、通用调用、结果格式化、工具列表输出和退出码处理。
- Create: `docs/superpowers/plans/2026-08-21-generic-mcp-client.md` — 本实施计划。

### Task 1: 先写客户端行为测试

**Files:**
- Create: `C:\Users\21776\Desktop\VibeChatbot\tests\test_mcp_client.py`

- [ ] **Step 1: 创建测试模块并从文件路径加载客户端**

由于仓库的 `mcp/` 目录没有包初始化文件，而 MCP 依赖本身也叫 `mcp`，测试通过文件路径加载本地客户端，避免把它解析成第三方包子模块：

```python
import asyncio
import contextlib
import io
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


CLIENT_PATH = Path(__file__).parents[1] / "mcp" / "client.py"
SPEC = importlib.util.spec_from_file_location("vibechatbot_mcp_client", CLIENT_PATH)
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)
```

- [ ] **Step 2: 写结果格式化的失败测试**

加入以下测试，先固定通用结果协议：

```python
class TestFormatToolResult(unittest.TestCase):
    def test_formats_text_content(self):
        result = SimpleNamespace(
            content=[SimpleNamespace(text="第一行"), SimpleNamespace(text="第二行")]
        )
        self.assertEqual(client.format_tool_result(result), "第一行\n第二行")

    def test_formats_unknown_content_and_structured_content(self):
        result = SimpleNamespace(
            content=[SimpleNamespace(type="image", data="abc")],
            structuredContent={"ok": True, "items": [1, 2]},
        )
        output = client.format_tool_result(result)
        self.assertIn("image", output)
        self.assertIn('"ok": true', output)

    def test_formats_empty_result_without_index_error(self):
        self.assertEqual(
            client.format_tool_result(SimpleNamespace(content=[])),
            "(empty result)",
        )
```

- [ ] **Step 3: 写通用参数解析和调用的失败测试**

加入以下测试，确保客户端只转发运行时提供的工具名和参数：

```python
class FakeSession:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.result


class TestGenericClient(unittest.TestCase):
    def test_parse_tool_arguments_defaults_to_empty_object(self):
        args = client.parse_arguments(["new_tool"])
        self.assertEqual(args.tool_name, "new_tool")
        self.assertEqual(args.arguments, {})

    def test_parse_tool_arguments_accepts_json_object(self):
        args = client.parse_arguments(["new_tool", '{"value": 7}'])
        self.assertEqual(args.arguments, {"value": 7})

    def test_parse_tool_arguments_rejects_non_object_json(self):
        with self.assertRaises(SystemExit):
            client.parse_arguments(["new_tool", "[1, 2]"])

    def test_parse_tool_arguments_rejects_invalid_json(self):
        with self.assertRaises(SystemExit):
            client.parse_arguments(["new_tool", "not-json"])

    def test_list_mode_does_not_require_tool_name(self):
        args = client.parse_arguments(["--list"])
        self.assertTrue(args.list_tools)
        self.assertIsNone(args.tool_name)

    def test_call_tool_forwards_any_tool_name_and_arguments(self):
        session = FakeSession(result="ok")
        result = asyncio.run(
            client.call_tool(session, "new_tool", {"value": 7})
        )
        self.assertEqual(result, "ok")
        self.assertEqual(session.calls, [("new_tool", {"value": 7})])

    def test_client_has_no_tool_specific_result_variables(self):
        source = CLIENT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("add_result", source)
        self.assertNotIn("echo_result", source)
```

- [ ] **Step 4: 写工具错误状态返回非零的失败测试**

为异步上下文和 `ClientSession` 增加最小替身，并验证服务端返回 `isError=True` 时 `run()` 返回 `1`：

```python
class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class ErrorSession(FakeSession):
    async def initialize(self):
        return None


class TestRun(unittest.TestCase):
    def test_error_result_returns_nonzero(self):
        session = ErrorSession(
            SimpleNamespace(
                content=[SimpleNamespace(text="tool failed")],
                isError=True,
            )
        )
        stderr = io.StringIO()
        with patch.object(
            client,
            "stdio_client",
            return_value=AsyncContext(("read", "write")),
        ), patch.object(
            client,
            "ClientSession",
            return_value=SessionContext(session),
        ), contextlib.redirect_stderr(stderr):
            exit_code = asyncio.run(client.run(["new_tool"]))

        self.assertEqual(exit_code, 1)
        self.assertIn("tool failed", stderr.getvalue())
```

- [ ] **Step 5: 运行新增测试，确认它们因接口尚未实现而失败**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_mcp_client.py -v
```

Expected: FAIL，失败原因应集中在 `parse_arguments`、`call_tool`、`format_tool_result` 或 `run` 尚不存在，而不是测试模块导入错误。

### Task 2: 实现通用 MCP 客户端

**Files:**
- Modify: `C:\Users\21776\Desktop\VibeChatbot\mcp\client.py`

- [ ] **Step 1: 替换硬编码客户端为通用实现**

保留 `SERVER_SCRIPT` 和 MCP stdio 依赖，使用以下完整实现结构：

```python
import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client


SERVER_SCRIPT = Path(__file__).resolve().parent / "server.py"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _content_text(item: Any) -> str:
    if isinstance(item, dict) and "text" in item:
        return str(item["text"])
    text = getattr(item, "text", None)
    if text is not None:
        return str(text)
    return _json_text(item)


def format_tool_result(result: Any) -> str:
    parts = [_content_text(item) for item in (getattr(result, "content", None) or [])]

    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is not None:
        parts.append(_json_text(structured))

    return "\n".join(parts) or "(empty result)"


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description="调用 MCP 服务端工具")
    parser.add_argument("--list", action="store_true", dest="list_tools")
    parser.add_argument("tool_name", nargs="?")
    parser.add_argument("arguments", nargs="?", default="{}")
    args = parser.parse_args(argv)

    if args.list_tools:
        if args.tool_name is not None:
            parser.error("--list 不能与工具名同时使用")
        args.arguments = {}
        return args

    if args.tool_name is None:
        parser.error("需要提供工具名，或使用 --list")

    try:
        args.arguments = json.loads(args.arguments)
    except json.JSONDecodeError as exc:
        parser.error(f"工具参数不是合法 JSON: {exc.msg}")
    if not isinstance(args.arguments, dict):
        parser.error("工具参数必须是 JSON 对象")
    return args


async def call_tool(session: ClientSession, tool_name: str, arguments: dict) -> Any:
    return await session.call_tool(tool_name, arguments)


def format_tool_list(result: Any) -> str:
    lines = ["tools:"]
    for tool in getattr(result, "tools", []) or []:
        description = getattr(tool, "description", None) or ""
        schema = getattr(tool, "inputSchema", None)
        suffix = f" inputSchema={_json_text(schema)}" if schema else ""
        lines.append(f"- {tool.name}: {description}{suffix}")
    return "\n".join(lines)


async def run(argv=None) -> int:
    args = parse_arguments(argv)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
    )

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                if args.list_tools:
                    print(format_tool_list(await session.list_tools()))
                    return 0

                result = await call_tool(session, args.tool_name, args.arguments)
                output = format_tool_result(result)
                if getattr(result, "isError", False):
                    print(output, file=sys.stderr)
                    return 1
                print(output)
                return 0
    except Exception as exc:
        print(f"MCP client error: {exc}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 运行新增测试，确认通用行为全部通过**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_mcp_client.py -v
```

Expected: 所有新增测试 PASS；测试源代码中不存在 `add_result`、`echo_result`。

- [ ] **Step 3: 检查客户端静态语义**

Run:

```powershell
Select-String -Path mcp/client.py -Pattern 'add_result|echo_result|call_tool\("add"|call_tool\("echo"'
```

Expected: 无匹配结果。

### Task 3: 运行真实 MCP 客户端和回归测试

**Files:**
- Test: `C:\Users\21776\Desktop\VibeChatbot\mcp\client.py`
- Test: `C:\Users\21776\Desktop\VibeChatbot\tests\test_mcp_client.py`

- [ ] **Step 1: 验证工具发现模式**

Run:

```powershell
.\.venv\Scripts\python.exe mcp\client.py --list
```

Expected: 输出服务端发现到的工具列表；客户端不自动执行任何固定工具。

- [ ] **Step 2: 验证任意工具调用模式**

Run:

```powershell
.\.venv\Scripts\python.exe mcp\client.py add '{"a":20,"b":22}'
.\.venv\Scripts\python.exe mcp\client.py echo '{"text":"hello from vibechatbot"}'
```

Expected: 第一条输出 `42`，第二条输出传入文本；两次调用均使用同一套通用结果处理。

- [ ] **Step 3: 运行全量 Python 回归测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected: 既有测试和新增客户端测试通过；若出现 Chroma 在 Windows 上的文件锁环境错误，记录具体失败用例和错误文本，不把它误报为客户端逻辑失败。

- [ ] **Step 4: 检查差异和工作区边界**

Run:

```powershell
git diff --check -- mcp/client.py tests/test_mcp_client.py
git status --short --branch
```

Expected: 新增实现只涉及 `mcp/client.py` 和 `tests/test_mcp_client.py`；不覆盖用户已有的 `pyproject.toml`、`requirements.txt` 或其他未跟踪内容。

- [ ] **Step 5: 提交实现与测试**

```powershell
git add -- mcp/client.py tests/test_mcp_client.py
git commit -m "feat: 通用化 MCP 客户端工具调用"
```

Expected: 只提交客户端实现和对应测试，设计文档提交 `285518c` 保持不变。
