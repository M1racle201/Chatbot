"""BaseAgent 与 AgentMessage 单元测试。"""

import asyncio
import unittest

from jobmatchagent.agents.base import AgentMessage, BaseAgent


class FakeAgent(BaseAgent):
    """最小可用子类:直接返回固定文本。"""

    def __init__(self, name="fake"):
        super().__init__(name=name)

    async def _process(self, message: AgentMessage) -> str:
        await asyncio.sleep(0)  # 模拟异步边界
        return "processed:" + message.task


class TestAgentMessage(unittest.TestCase):
    def test_defaults(self):
        message = AgentMessage(task="hello")
        self.assertEqual(message.task, "hello")
        self.assertEqual(message.context, {})
        self.assertEqual(message.output, "")
        self.assertEqual(message.meta, {})


class TestBaseAgent(unittest.TestCase):
    def test_run_returns_output_in_message(self):
        agent = FakeAgent("a1")
        message = asyncio.run(agent.run(AgentMessage(task="hello")))
        self.assertEqual(message.output, "processed:hello")
        self.assertEqual(message.meta["agent"], "a1")

    def test_run_records_process_log(self):
        agent = FakeAgent("a1")
        message = asyncio.run(agent.run(AgentMessage(task="x")))
        log = message.meta["process_log"]
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["event"], "start")
        self.assertEqual(log[0]["agent"], "a1")
        self.assertEqual(log[1]["event"], "end")
        self.assertIn("elapsed_ms", message.meta)

    def test_abstract_process_raises(self):
        class Incomplete(BaseAgent):
            pass

        with self.assertRaises(NotImplementedError):
            asyncio.run(Incomplete("inc").run(AgentMessage(task="x")))

    def test_error_recorded_and_raised(self):
        class Boom(BaseAgent):
            async def _process(self, message: AgentMessage) -> str:
                raise ValueError("boom")

        agent = Boom("b")
        with self.assertRaises(ValueError):
            asyncio.run(agent.run(AgentMessage(task="x")))
        self.assertEqual(agent.last_message.meta["error"], "boom")


if __name__ == "__main__":
    unittest.main()
