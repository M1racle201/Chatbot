import asyncio
import contextlib
import importlib.util
import io
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


CLIENT_PATH = Path(__file__).parents[1] / "mcp" / "client.py"
SPEC = importlib.util.spec_from_file_location("vibechatbot_mcp_client", CLIENT_PATH)
client = importlib.util.module_from_spec(SPEC)
PROJECT_ROOT = CLIENT_PATH.parents[1]
ORIGINAL_SYS_PATH = sys.path[:]
sys.path = [
    entry
    for entry in sys.path
    if Path(entry or ".").resolve() != PROJECT_ROOT.resolve()
]
try:
    SPEC.loader.exec_module(client)
finally:
    sys.path = ORIGINAL_SYS_PATH


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
