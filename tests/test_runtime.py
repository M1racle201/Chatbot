"""runtime.run_task 统一路由与会话存档单元测试（注入 fake 组件，不联网）。"""

import json
import os
import tempfile
import unittest

from vibechatbot.agents.base import AgentMessage
from vibechatbot.runtime import Runtime


class FakeAgent:
    """快速通道 fake：记录收到的上下文，返回固定结论。"""

    def __init__(self):
        self.last_messages = [{"role": "system", "content": "s"}]
        self.last_context = None

    def run(self, task, context=None):
        self.last_context = context
        return "快速通道输出"


class FakePipeline:
    """流水线 fake：记录收到的上下文，返回固定判定。"""

    def __init__(self):
        self.attempts = {"rewrite": 1, "research": 2}
        self.last_steps = [{"agent": "fake"}]
        self.last_context = None

    async def run(self, task, context=None, stream_callback=None):
        self.last_context = context
        if stream_callback:
            stream_callback("streaming")
        return AgentMessage(
            task=task,
            output="流水线候选结论",
            meta={
                "verdict": {"passed": False, "reason": "缺少依据", "exhausted": True},
                "candidate": "最终结论",
            },
        )


class TestRuntime(unittest.TestCase):
    def _make_runtime(self, simple_route=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Runtime(
            chat=None,
            agent=FakeAgent(),
            pipeline=FakePipeline(),
            is_simple_tool_task=lambda task: simple_route,
            session_dir=tmp.name,
        )

    def test_fast_path_routes_to_agent(self):
        runtime = self._make_runtime(simple_route=True)
        result = runtime.run_task("保存文件")
        self.assertEqual(result["route"], "fast")
        self.assertEqual(result["output"], "快速通道输出")

    def test_pipeline_route_returns_verdict_and_attempts(self):
        runtime = self._make_runtime(simple_route=False)
        result = runtime.run_task("知识库问答")
        self.assertEqual(result["route"], "pipeline")
        self.assertEqual(result["output"], "最终结论")
        self.assertTrue(result["verdict"]["exhausted"])
        self.assertEqual(result["attempts"], {"rewrite": 1, "research": 2})

    def test_session_archives_all_tasks_into_one_file(self):
        runtime = self._make_runtime(simple_route=False)
        runtime.run_task("任务1")
        runtime.run_task("任务2")
        files = os.listdir(runtime.session_dir)
        self.assertEqual(len(files), 1)
        with open(runtime.session_file, encoding="utf-8") as file:
            data = json.load(file)
        self.assertEqual(len(data["session"]), 2)
        self.assertEqual(data["session"][0]["task"], "任务1")
        self.assertEqual(data["session"][1]["task"], "任务2")

    def test_session_context_injected_from_previous_task(self):
        runtime = self._make_runtime(simple_route=False)
        runtime.run_task("先看文件")
        runtime.run_task("修改文件")
        context = runtime.pipeline.last_context
        self.assertIsNotNone(context)
        self.assertIn("先看文件", context["session_history"])
        self.assertIn("最终结论", context["session_history"])
        # 当前任务本身不进入上下文，只有之前的对话
        self.assertNotIn("修改文件", context["session_history"])


if __name__ == "__main__":
    unittest.main()
