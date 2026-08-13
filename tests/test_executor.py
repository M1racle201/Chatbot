"""ExecutorAgent(Agent2 主题执行器)单元测试。"""

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
    """按顺序返回预设响应,并记录每次收到的 messages。"""

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


class FakeStreamChat:
    """fake chat：按顺序返回 (content, tool_calls)，触发流式回调。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def compress_messages(self, messages):
        return messages

    def stream_completion(self, messages, tools=None, on_chunk=None):
        self.calls.append((messages, tools))
        content, tool_calls = self.responses.pop(0)
        if content and on_chunk:
            on_chunk(content)
        return content, tool_calls


class TestExecutorAgent(unittest.TestCase):
    def test_direct_reply(self):
        llm = SequentialLLM([FakeResponse(FakeMessage(content="结论文本"))])
        agent = ExecutorAgent(llm=llm)
        message = asyncio.run(agent.run(AgentMessage(task="问题")))
        self.assertEqual(message.output, "结论文本")
        # 首条消息应是执行器提示词(含检索规范)
        self.assertEqual(llm.calls[0][0]["role"], "system")
        self.assertIn("检索", llm.calls[0][0]["content"])

    def test_tool_loop(self):
        calls = []

        def fake_tool(name, arguments):
            calls.append((name, arguments))
            return '{"ok": true}'

        fake_tools = [{"type": "function", "function": {"name": "query_documents"}}]
        llm = SequentialLLM(
            [
                tool_call_response(
                    "query_documents", '{"query": "向量库", "top_k": 3}'
                ),
                FakeResponse(FakeMessage(content="基于检索的结论")),
            ]
        )
        agent = ExecutorAgent(llm=llm, tool_executor=fake_tool, tools=fake_tools)
        message = asyncio.run(agent.run(AgentMessage(task="向量库是什么")))
        self.assertEqual(message.output, "基于检索的结论")
        self.assertEqual(calls, [("query_documents", {"query": "向量库", "top_k": 3})])
        # 注入的 llm 应收到工具定义(与真实路径行为一致)
        self.assertEqual(llm.calls_tools[0], fake_tools)
        # 第二轮请求应包含 tool 结果消息
        second_messages = llm.calls[1]
        self.assertEqual(second_messages[-1]["role"], "tool")
        self.assertEqual(second_messages[-1]["tool_call_id"], "call_1")

    def test_max_steps_guard(self):
        llm = SequentialLLM(
            [
                tool_call_response(
                    "load" if i % 2 == 0 else "query_documents",
                    '{"path": "a.txt"}' if i % 2 == 0 else '{"query": "x"}',
                    call_id=f"c{i}",
                )
                for i in range(50)
            ]
        )
        def fake_tool(name, arguments):
            return "[]"

        agent = ExecutorAgent(llm=llm, max_steps=3, tool_executor=fake_tool)
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertEqual(message.output, "已达最大执行步数,未能生成结论")

    def test_compress_when_messages_exceed(self):
        llm = SequentialLLM(
            [
                tool_call_response(
                    "load" if i % 2 == 0 else "query_documents",
                    '{"path": "a.txt"}' if i % 2 == 0 else '{"query": "x"}',
                    call_id=f"c{i}",
                )
                for i in range(50)
            ]
        )
        # max_messages 调小,快速触发上下文压缩
        def fake_tool(name, arguments):
            return "[]"

        agent = ExecutorAgent(llm=llm, max_steps=8, max_messages=6, tool_executor=fake_tool)
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertEqual(message.output, "已达最大执行步数,未能生成结论")
        # 找到第一次压缩后的调用:首条是 system 提示词,第二条是进度总结
        compressed_call = next(
            call for call in llm.calls
            if call[1].get("role") == "system" and "进度总结" in call[1]["content"]
        )
        self.assertEqual(compressed_call[0]["role"], "system")
        self.assertEqual(compressed_call[0]["content"], agent.executor_prompt)

    def test_bad_tool_arguments_tolerated(self):
        def fake_tool(name, arguments):
            return "[]"

        llm = SequentialLLM(
            [
                tool_call_response("load", "not-json{{{"),
                FakeResponse(FakeMessage(content="ok")),
            ]
        )
        agent = ExecutorAgent(llm=llm, tool_executor=fake_tool)
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertEqual(message.output, "ok")

    def test_prompt_file_missing_falls_back(self):
        llm = SequentialLLM([FakeResponse(FakeMessage(content="ok"))])
        agent = ExecutorAgent(llm=llm, prompt_file="nonexistent/path/executor")
        self.assertTrue(agent.executor_prompt.strip())

    def test_convergence_early_exit(self):
        """连续多轮请求相同工具时提前收敛,不跑满 max_steps。"""
        def fake_tool(name, arguments):
            return "[]"

        same_call = tool_call_response(
            "query_documents", '{"query": "一样的问题"}', call_id="c1"
        )
        llm = SequentialLLM(
            [same_call, same_call, same_call]
            + [tool_call_response("load", '{"path": "a.txt"}', call_id=f"c{i}")
               for i in range(20)]
        )
        agent = ExecutorAgent(llm=llm, tool_executor=fake_tool, max_steps=10)
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertIn("收敛", message.output)
        self.assertEqual(len(llm.calls), 3)  # 第 3 轮快照后触发收敛

    def test_no_convergence_when_different(self):
        """工具调用持续变化时不收敛,正常走到结论。"""
        def fake_tool(name, arguments):
            return "[]"

        llm = SequentialLLM(
            [
                tool_call_response("query_documents", '{"query": "问题1"}', "c1"),
                tool_call_response("query_documents", '{"query": "问题2"}', "c2"),
                tool_call_response("load", '{"path": "a.txt"}', "c3"),
                FakeResponse(FakeMessage(content="结论")),
            ]
        )
        agent = ExecutorAgent(llm=llm, tool_executor=fake_tool)
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertEqual(message.output, "结论")

    def test_evidence_collected_from_query_documents(self):
        """query_documents 的检索片段应写入 context["evidence"]。"""
        def fake_tool(name, arguments):
            return json.dumps({
                "query": "x",
                "results": [
                    {"content": "片段A内容", "source": "a.pdf"},
                    {"content": "片段B内容", "source": "b.docx"},
                ],
            })

        llm = SequentialLLM(
            [
                tool_call_response("query_documents", '{"query": "x"}', "c1"),
                FakeResponse(FakeMessage(content="结论")),
            ]
        )
        agent = ExecutorAgent(llm=llm, tool_executor=fake_tool)
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertEqual(
            message.context["evidence"],
            [
                {"source": "a.pdf", "content": "片段A内容"},
                {"source": "b.docx", "content": "片段B内容"},
            ],
        )

    def test_evidence_truncated(self):
        """超长片段截断,且数量不超过上限。"""
        long_text = "长" * 2000

        def fake_tool(name, arguments):
            return json.dumps({
                "results": [
                    {"content": long_text, "source": "a.pdf"},
                    {"content": "片段B", "source": "b.pdf"},
                    {"content": "片段C", "source": "c.pdf"},
                    {"content": "片段D", "source": "d.pdf"},
                ]
            })

        llm = SequentialLLM(
            [
                tool_call_response("query_documents", '{"query": "x"}', "c1"),
                FakeResponse(FakeMessage(content="结论")),
            ]
        )
        agent = ExecutorAgent(
            llm=llm,
            tool_executor=fake_tool,
            max_evidence_items=3,
            max_evidence_chars=500,
        )
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        evidence = message.context["evidence"]
        self.assertEqual(len(evidence), 3)  # 上限 3 条
        self.assertEqual(len(evidence[0]["content"]), 500)  # 截断到 500 字
        self.assertEqual(evidence[-1]["source"], "c.pdf")

    def test_no_llm_and_no_chat_raises(self):
        with self.assertRaises(ValueError):
            ExecutorAgent()

    def test_stream_callback_used_when_chat_configured(self):
        fake_chat = FakeStreamChat(
            [
                (
                    "",
                    [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "query_documents",
                                "arguments": '{"query": "x"}',
                            },
                        }
                    ],
                ),
                ("final-stream", []),
            ]
        )
        chunks = []
        agent = ExecutorAgent(
            chat=fake_chat,
            tools=[],
            tool_executor=lambda name, arguments: '{"ok": true}',
        )
        agent.stream_callback = chunks.append
        message = asyncio.run(agent.run(AgentMessage(task="问题")))
        self.assertEqual(message.output, "final-stream")
        self.assertEqual(chunks, ["final-stream"])
        # 流式路径把工具定义传给了 chat
        self.assertEqual(fake_chat.calls[0][1], [])


if __name__ == "__main__":
    unittest.main()
