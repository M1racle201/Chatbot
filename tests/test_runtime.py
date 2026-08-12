"""runtime.run_task 统一路由单元测试（注入 fake 组件，不联网）。"""

import unittest

from vibechatbot.agents.base import AgentMessage
from vibechatbot.runtime import Runtime


class FakeAgent:
    def run(self, task):
        return "快速通道输出"


class FakePipeline:
    def __init__(self):
        self.attempts = {"rewrite": 1, "research": 2}

    async def run(self, task):
        return AgentMessage(
            task=task,
            output="流水线候选结论",
            meta={
                "verdict": {"passed": False, "reason": "缺少依据", "exhausted": True},
                "candidate": "最终结论",
            },
        )


class TestRuntime(unittest.TestCase):
    def test_fast_path_routes_to_agent(self):
        runtime = Runtime(
            chat=None,
            agent=FakeAgent(),
            pipeline=None,
            is_simple_tool_task=lambda task: True,
        )
        result = runtime.run_task("保存文件")
        self.assertEqual(result["route"], "fast")
        self.assertEqual(result["output"], "快速通道输出")

    def test_pipeline_route_returns_verdict_and_attempts(self):
        runtime = Runtime(
            chat=None,
            agent=FakeAgent(),
            pipeline=FakePipeline(),
            is_simple_tool_task=lambda task: False,
        )
        result = runtime.run_task("知识库问答")
        self.assertEqual(result["route"], "pipeline")
        self.assertEqual(result["output"], "最终结论")
        self.assertTrue(result["verdict"]["exhausted"])
        self.assertEqual(result["attempts"], {"rewrite": 1, "research": 2})


if __name__ == "__main__":
    unittest.main()
