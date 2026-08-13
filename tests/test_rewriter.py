"""RewriterAgent(Agent1 复写器)单元测试。"""

import asyncio
import unittest

from vibechatbot.agents.base import AgentMessage
from vibechatbot.agents.rewriter import RewriterAgent


class FakeLLM:
    """记录收到的 messages,返回固定复写文本。"""

    def __init__(self, reply="rewritten text"):
        self.reply = reply
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return self.reply


class TestRewriterAgent(unittest.TestCase):
    def test_rewrites_task(self):
        llm = FakeLLM("请解释向量数据库的原理")
        agent = RewriterAgent(llm=llm)
        message = asyncio.run(agent.run(AgentMessage(task="向量库是啥")))
        self.assertEqual(message.output, "请解释向量数据库的原理")

    def test_messages_structure(self):
        llm = FakeLLM()
        agent = RewriterAgent(llm=llm)
        asyncio.run(agent.run(AgentMessage(task="向量库是啥")))
        sent = llm.calls[0]
        self.assertEqual(sent[0]["role"], "system")
        self.assertEqual(sent[1], {"role": "user", "content": "向量库是啥"})
        self.assertTrue(sent[0]["content"].strip())

    def test_async_llm_supported(self):
        async def async_llm(messages):
            return "async reply"

        agent = RewriterAgent(llm=async_llm)
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertEqual(message.output, "async reply")

    def test_prompt_file_missing_falls_back(self):
        llm = FakeLLM()
        agent = RewriterAgent(llm=llm, prompt_file="nonexistent/path/rewriter")
        self.assertTrue(agent.rewrite_prompt.strip())

    def test_no_llm_and_no_chat_raises(self):
        with self.assertRaises(ValueError):
            RewriterAgent()

    def test_run_records_meta(self):
        llm = FakeLLM("r")
        agent = RewriterAgent(llm=llm)
        message = asyncio.run(agent.run(AgentMessage(task="t")))
        self.assertEqual(message.meta["agent"], "rewriter")
        self.assertIn("elapsed_ms", message.meta)

    def test_chat_uses_non_stream_when_no_llm(self):
        """chat 分支走非流式：中间产物不需要流式输出。"""

        class FakeChat:
            model = "test-model"

            def _create_with_retry(self, model, messages):
                msg = type("Msg", (), {"content": "非流式改写"})()
                choice = type("Choice", (), {"message": msg})()
                return type("Resp", (), {"choices": [choice]})()

        agent = RewriterAgent(chat=FakeChat())
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertEqual(message.output, "非流式改写")


if __name__ == "__main__":
    unittest.main()
