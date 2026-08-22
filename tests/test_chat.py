"""Chat.compress_messages（任务内消息压缩逻辑）单元测试。"""

import os
import tempfile
import unittest
from types import SimpleNamespace

from jobmatchagent.chat import Chat
from jobmatchagent.history import History


def _server_error():
    """构造真实的 openai InternalServerError，用于模拟流式中断重试。"""
    import httpx
    from openai import InternalServerError
    response = httpx.Response(
        500, request=httpx.Request("POST", "https://api.test")
    )
    return InternalServerError(
        "server error", response=response, body=None
    )


class TestCompressMessages(unittest.TestCase):
    """跳过 __init__ 构造 Chat，只验证 compress_messages 的轮次压缩规则。"""

    def _make_chat(self, max_rounds=2, keep_recent_rounds=1):
        chat = Chat.__new__(Chat)
        chat.history = History(
            os.path.join(tempfile.gettempdir(), "compress_messages_test.json")
        )
        chat.max_rounds = max_rounds
        chat.keep_recent_rounds = keep_recent_rounds
        chat._summarize_messages = lambda messages: "总结"
        return chat

    def test_within_round_limit_returns_same_list(self):
        chat = self._make_chat(max_rounds=3)
        messages = [
            {"role": "system", "content": "提示词"},
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
        ]
        self.assertIs(chat.compress_messages(messages), messages)

    def test_compress_keeps_system_summary_and_recent(self):
        chat = self._make_chat(max_rounds=1, keep_recent_rounds=1)
        messages = [
            {"role": "system", "content": "提示词"},
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
            {"role": "user", "content": "问题2"},
            {"role": "assistant", "content": "回答2"},
            {"role": "user", "content": "问题3"},
            {"role": "assistant", "content": "回答3"},
        ]
        result = chat.compress_messages(messages)
        self.assertEqual(result[0]["content"], "提示词")
        self.assertEqual(result[1]["content"], "对话总结：总结")
        contents = [m["content"] for m in result]
        self.assertNotIn("问题1", contents)
        self.assertIn("问题3", contents)
        self.assertIn("回答3", contents)

    def test_compress_starts_from_assistant_to_keep_tool_pair(self):
        chat = self._make_chat(max_rounds=1, keep_recent_rounds=1)
        messages = [
            {"role": "system", "content": "提示词"},
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
            {"role": "user", "content": "问题2"},
            {"role": "assistant", "content": "回答2"},
            {"role": "user", "content": "问题3"},
            {"role": "assistant", "content": "回答3"},
            {"role": "tool", "content": "结果3"},
        ]
        result = chat.compress_messages(messages)
        # 按条数保留最近片段，tool 跟在 assistant 之后、不孤立
        self.assertEqual(result[2]["role"], "assistant")
        self.assertEqual(result[-1]["role"], "tool")

    def test_compress_drops_leading_orphan_tool_messages(self):
        chat = self._make_chat(max_rounds=1, keep_recent_rounds=1)
        messages = [
            {"role": "system", "content": "提示词"},
            {"role": "user", "content": "问题1"},
            {"role": "assistant", "content": "回答1"},
            {"role": "user", "content": "问题2"},
            {"role": "assistant", "content": "回答2"},
            {"role": "user", "content": "问题3"},
            {"role": "assistant", "content": "回答3"},
            {"role": "tool", "content": "结果3a"},
            {"role": "tool", "content": "结果3b"},
        ]
        result = chat.compress_messages(messages)
        # 开头的孤立 tool 被丢弃，只剩 system 前缀
        self.assertEqual([m["role"] for m in result], ["system", "system"])


class TestStreamCompletion(unittest.TestCase):
    """Verify stream_completion text/tool-call aggregation and callback."""

    def _make_stream_chat(self, chunks):
        chat = Chat.__new__(Chat)
        chat.model = "test-model"
        chat._stream_with_retry = lambda **kwargs: iter(chunks)
        return chat

    def _chunk(self, content=None, tool_calls=None):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=content, tool_calls=tool_calls)
                )
            ]
        )

    def test_stream_completion_aggregates_text_and_calls_back(self):
        chat = self._make_stream_chat(
            [self._chunk("你"), self._chunk("好"), SimpleNamespace(choices=[])]
        )
        received = []
        content, tool_calls = chat.stream_completion(
            [{"role": "user", "content": "hi"}], on_chunk=received.append
        )
        self.assertEqual(content, "你好")
        self.assertEqual(received, ["你", "好"])
        self.assertEqual(tool_calls, [])

    def test_stream_completion_sends_stream_flag(self):
        """回归：流式请求必须传 stream=True，否则 API 返回非流式对象。"""
        received = {}

        def fake_stream(**kwargs):
            received.update(kwargs)
            return iter([self._chunk("ok")])

        chat = Chat.__new__(Chat)
        chat.model = "test-model"
        chat._stream_with_retry = fake_stream
        chat.stream_completion([])
        self.assertIs(received.get("stream"), True)

    def test_stream_completion_skips_duplicate_prefix_after_retry(self):
        """回归：流式中断重试后，已发送文本不再重复输出。"""

        attempts = {"n": 0}

        def fake_create(**kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                def first():
                    yield self._chunk("你好")
                    raise _server_error()
                return first()
            def second():
                yield self._chunk("你好")
                yield self._chunk("世界")
            return second()

        chat = Chat.__new__(Chat)
        chat.model = "test-model"
        chat.max_retries = 3
        chat.retry_delay = 1
        chat._wait_and_report = lambda exc, attempt: None
        chat.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        received = []
        content, tool_calls = chat.stream_completion([], on_chunk=received.append)
        self.assertEqual(content, "你好世界")
        # 中断前已发送的"你好" + 重试后补齐的"世界"，无重复
        self.assertEqual(received, ["你好", "世界"])
        self.assertEqual(attempts["n"], 2)

    def test_stream_completion_skips_duplicate_tool_calls_after_retry(self):
        """回归：流式中断重试后，工具调用参数不重复拼接。"""

        attempts = {"n": 0}

        def tool_chunk():
            return self._chunk(
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call_1",
                        function=SimpleNamespace(
                            name="load", arguments='{"file": "a.txt"}'
                        ),
                    )
                ]
            )

        def fake_create(**kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                def first():
                    yield tool_chunk()
                    raise _server_error()
                return first()
            def second():
                yield tool_chunk()
            return second()

        chat = Chat.__new__(Chat)
        chat.model = "test-model"
        chat.max_retries = 3
        chat.retry_delay = 1
        chat._wait_and_report = lambda exc, attempt: None
        chat.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        content, tool_calls = chat.stream_completion([])
        self.assertEqual(content, "")
        self.assertEqual(
            tool_calls,
            [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "load", "arguments": '{"file": "a.txt"}'},
                }
            ],
        )

    def test_stream_completion_aggregates_tool_call_deltas(self):
        chat = self._make_stream_chat(
            [
                self._chunk(
                    tool_calls=[
                        SimpleNamespace(
                            index=0,
                            id="call_1",
                            function=SimpleNamespace(
                                name="load", arguments='{"file":'
                            ),
                        )
                    ]
                ),
                self._chunk(
                    tool_calls=[
                        SimpleNamespace(
                            index=0,
                            id="",
                            function=SimpleNamespace(
                                name=None, arguments=' "a.txt"}'
                            ),
                        )
                    ]
                ),
                self._chunk(content="done"),
            ]
        )
        content, tool_calls = chat.stream_completion([])
        self.assertEqual(content, "done")
        self.assertEqual(
            tool_calls,
            [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "load", "arguments": '{"file": "a.txt"}'},
                }
            ],
        )
