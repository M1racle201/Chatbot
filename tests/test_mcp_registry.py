import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from vibechatbot import mcp_registry


class AsyncContext:
    def __init__(self, value):
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        self.exited = True
        return False


class FakeSession:
    def __init__(self, tools=None, result=None):
        self.tools = tools or []
        self.result = result
        self.calls = []
        self.initialized = False

    async def initialize(self):
        self.initialized = True

    async def list_tools(self):
        return SimpleNamespace(tools=self.tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.result


class FailingSession(FakeSession):
    async def initialize(self):
        raise RuntimeError("initialize failed")


class TestMCPRegistryConfig(unittest.TestCase):
    def test_missing_config_returns_empty_registry(self):
        registry = mcp_registry.MCPRegistry.from_config("missing-mcp-config.json")
        self.assertEqual(registry.server_names(), [])

    def test_config_keeps_command_args_and_resolves_env_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mcp.json"
            path.write_text(
                json.dumps(
                    {
                        "servers": {
                            "browser": {
                                "enabled": True,
                                "command": "node",
                                "args": ["server.js", "--watch"],
                                "env": ["BROWSER_TOKEN"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"BROWSER_TOKEN": "secret"}, clear=False):
                registry = mcp_registry.MCPRegistry.from_config(str(path))

        self.assertEqual(registry.server_names(), ["browser"])
        self.assertEqual(registry.server_specs()[0].command, "node")
        self.assertEqual(registry.server_specs()[0].args, ("server.js", "--watch"))
        self.assertEqual(
            registry.server_specs()[0].environment["BROWSER_TOKEN"],
            "secret",
        )

    def test_disabled_server_does_not_enter_server_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mcp.json"
            path.write_text(
                json.dumps(
                    {
                        "servers": {
                            "browser": {
                                "enabled": False,
                                "command": "node",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            registry = mcp_registry.MCPRegistry.from_config(str(path))

        self.assertEqual(registry.server_names(), [])


class TestMCPRegistryCalls(unittest.TestCase):
    def test_from_server_specs_accepts_dictionary_input(self):
        registry = mcp_registry.MCPRegistry.from_server_specs(
            {
                "browser": {
                    "command": "node",
                    "args": ["server.js"],
                }
            }
        )

        self.assertEqual(registry.server_names(), ["browser"])
        self.assertEqual(registry.server_specs()[0].command, "node")
        self.assertEqual(registry.server_specs()[0].args, ("server.js",))

    def test_from_server_specs_accepts_list_input(self):
        registry = mcp_registry.MCPRegistry.from_server_specs(
            [{"name": "browser", "command": "node", "args": ["server.js"]}]
        )

        self.assertEqual(registry.server_names(), ["browser"])

    def test_discovers_namespaced_tool_and_forwards_original_name(self):
        session = FakeSession(
            tools=[
                SimpleNamespace(
                    name="search",
                    description="Search the web",
                    inputSchema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                )
            ],
            result=SimpleNamespace(content=[SimpleNamespace(text="ok")]),
        )
        registry = mcp_registry.MCPRegistry.from_server_specs(
            [{"name": "browser", "command": "node", "args": []}]
        )
        stdio_context = AsyncContext(("read", "write"))
        session_context = AsyncContext(session)

        with patch.object(
            mcp_registry,
            "stdio_client",
            return_value=stdio_context,
            create=True,
        ), patch.object(
            mcp_registry,
            "ClientSession",
            return_value=session_context,
            create=True,
        ):

            async def scenario():
                async with registry:
                    definitions = registry.tool_definitions()
                    result = await registry.call(
                        "browser__search", {"query": "python"}
                    )
                    return definitions, result

            definitions, result = asyncio.run(scenario())

        self.assertEqual(definitions[0]["function"]["name"], "browser__search")
        self.assertTrue(session.initialized)
        self.assertEqual(session.calls, [("search", {"query": "python"})])
        self.assertEqual(result, "ok")
        self.assertTrue(stdio_context.exited)
        self.assertTrue(session_context.exited)

    def test_structured_content_takes_priority_over_text(self):
        session = FakeSession(
            result=SimpleNamespace(
                content=[SimpleNamespace(text="fallback text")],
                structuredContent={"items": [{"url": "https://example.com"}]},
            )
        )
        registry = mcp_registry.MCPRegistry.from_server_specs(
            [{"name": "browser", "command": "node", "args": []}]
        )

        with patch.object(
            mcp_registry,
            "stdio_client",
            return_value=AsyncContext(("read", "write")),
            create=True,
        ), patch.object(
            mcp_registry,
            "ClientSession",
            return_value=AsyncContext(session),
            create=True,
        ):

            async def scenario():
                async with registry:
                    return await registry.call("browser__search", {"query": "python"})

            result = asyncio.run(scenario())

        payload = json.loads(result)
        self.assertTrue(session.initialized)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["items"][0]["url"], "https://example.com")

    def test_is_error_results_include_top_level_error(self):
        session = FakeSession(
            result=SimpleNamespace(
                content=[SimpleNamespace(text="blocked")],
                isError=True,
            )
        )
        registry = mcp_registry.MCPRegistry.from_server_specs(
            [{"name": "browser", "command": "node", "args": []}]
        )

        with patch.object(
            mcp_registry,
            "stdio_client",
            return_value=AsyncContext(("read", "write")),
            create=True,
        ), patch.object(
            mcp_registry,
            "ClientSession",
            return_value=AsyncContext(session),
            create=True,
        ):

            async def scenario():
                async with registry:
                    return await registry.call("browser__search", {"query": "python"})

            result = asyncio.run(scenario())

        payload = json.loads(result)
        self.assertTrue(session.initialized)
        self.assertIsInstance(payload, dict)
        self.assertIsInstance(payload["error"], str)
        self.assertIn("blocked", payload["error"])

    def test_unknown_tool_results_include_top_level_error(self):
        registry = mcp_registry.MCPRegistry.from_server_specs([])

        result = asyncio.run(registry.call("browser__missing", {}))

        payload = json.loads(result)
        self.assertIsInstance(payload, dict)
        self.assertIsInstance(payload["error"], str)
        self.assertIn("browser__missing", payload["error"])


class TestMCPRegistryStartupFailure(unittest.TestCase):
    def test_startup_failure_closes_entered_contexts_and_raises_registry_error(self):
        first_context = AsyncContext(("read-1", "write-1"))
        second_context = AsyncContext(("read-2", "write-2"))
        first_session = FakeSession()
        second_session = FailingSession()

        registry = mcp_registry.MCPRegistry.from_server_specs(
            [
                {"name": "browser", "command": "node", "args": []},
                {"name": "broken", "command": "node", "args": []},
            ]
        )

        with patch.object(
            mcp_registry,
            "stdio_client",
            side_effect=[first_context, second_context],
            create=True,
        ), patch.object(
            mcp_registry,
            "ClientSession",
            side_effect=[
                AsyncContext(first_session),
                AsyncContext(second_session),
            ],
            create=True,
        ):

            async def scenario():
                with self.assertRaises(mcp_registry.MCPRegistryError) as ctx:
                    async with registry:
                        pass
                return ctx.exception

            error = asyncio.run(scenario())

        self.assertTrue(first_context.entered)
        self.assertTrue(first_context.exited)
        self.assertTrue(second_context.entered)
        self.assertTrue(second_context.exited)
        self.assertIn("broken", str(error))


if __name__ == "__main__":
    unittest.main()
