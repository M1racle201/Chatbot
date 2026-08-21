"""ExecutorAgent MCP 集成测试。"""

import asyncio
import json
import unittest

from vibechatbot.agents.base import AgentMessage
from vibechatbot.agents.executor import ExecutorAgent


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self):
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": self.tool_calls,
        }


class FakeResponse:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


class SequentialLLM:
    """按顺序返回预设响应,并记录收到的消息与工具定义。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.calls_tools = []

    def __call__(self, messages, tools=None):
        self.calls.append(messages)
        self.calls_tools.append(tools)
        return self.responses.pop(0)


def tool_call_response(name, arguments, call_id="call_1"):
    message = FakeMessage(
        tool_calls=[
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ]
    )
    return FakeResponse(message)


class FakeRegistry:
    def __init__(self):
        self.calls = []
        self.response = json.dumps(
            {
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com",
                        "content": "Example body",
                    }
                ]
            },
            ensure_ascii=False,
        )

    def tool_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "browser__search",
                    "description": "Search the web",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

    def has_tool(self, name):
        return name == "browser__search"

    async def call(self, name, args):
        self.calls.append((name, args))
        return self.response


class TestExecutorMCPIntegration(unittest.TestCase):
    def test_mcp_registry_tools_are_merged_and_browser_call_uses_registry(self):
        registry = FakeRegistry()
        local_tools = [
            {
                "type": "function",
                "function": {
                    "name": "save_file",
                    "description": "Save text to file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            }
        ]
        llm = SequentialLLM(
            [
                tool_call_response("browser__search", '{"query":"python"}', "mcp_1"),
                FakeResponse(FakeMessage(content="第二轮最终文本")),
            ]
        )
        local_calls = []

        def local_tool_executor(name, arguments):
            local_calls.append((name, arguments))
            return json.dumps({"ok": True}, ensure_ascii=False)

        agent = ExecutorAgent(
            llm=llm,
            tools=local_tools,
            tool_executor=local_tool_executor,
        )
        agent.set_mcp_registry(registry)

        message = asyncio.run(agent.run(AgentMessage(task="查找 python")))

        self.assertEqual(message.output, "第二轮最终文本")
        self.assertEqual(len(llm.calls_tools), 2)
        self.assertCountEqual(
            [tool["function"]["name"] for tool in llm.calls_tools[0]],
            ["save_file", "browser__search"],
        )
        self.assertEqual(
            registry.calls,
            [("browser__search", {"query": "python"})],
        )
        self.assertEqual(local_calls, [])
        self.assertEqual(llm.calls[1][-1]["role"], "tool")
        self.assertEqual(llm.calls[1][-1]["content"], registry.response)


class TestExecutorEvidenceFromBrowserTools(unittest.TestCase):
    def test_browser_results_populate_evidence_from_url_and_body(self):
        browser_result = json.dumps(
            {
                "results": [
                    {
                        "title": "Example Title",
                        "url": "https://example.com",
                        "content": "Example body",
                    }
                ]
            },
            ensure_ascii=False,
        )

        def fake_tool_executor(name, arguments):
            return browser_result

        llm = SequentialLLM(
            [
                tool_call_response(
                    "browser__anything",
                    '{"query":"python"}',
                    "browser_1",
                ),
                FakeResponse(FakeMessage(content="结论")),
            ]
        )
        agent = ExecutorAgent(llm=llm, tool_executor=fake_tool_executor)

        message = asyncio.run(agent.run(AgentMessage(task="浏览网页")))

        self.assertIn("evidence", message.context)
        self.assertGreaterEqual(len(message.context["evidence"]), 1)
        self.assertEqual(message.context["evidence"][0]["source"], "https://example.com")
        self.assertIn("Example Title", message.context["evidence"][0]["content"])
        self.assertIn("Example body", message.context["evidence"][0]["content"])


if __name__ == "__main__":
    unittest.main()
