"""runtime.run_task 统一路由与会话存档单元测试（注入 fake 组件，不联网）。"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from vibechatbot.agents.base import AgentMessage
from vibechatbot.runtime import Runtime, build_runtime


class FakeChat:
    """带 _summarize_messages 的 fake，用于验证上下文改为摘要生成。"""

    def __init__(self):
        self.summarized = None

    def _summarize_messages(self, messages):
        self.summarized = messages
        return "摘要：先看文件 -> 最终结论"


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

    async def run(
        self, task, context=None, stream_callback=None, step_callback=None
    ):
        self.last_context = context
        if stream_callback:
            stream_callback("streaming")
        if step_callback:
            step_callback("verify_pass", "核查通过")
        return AgentMessage(
            task=task,
            output="流水线候选结论",
            meta={
                "verdict": {"passed": False, "reason": "缺少依据", "exhausted": True},
                "candidate": "最终结论",
            },
        )


class FakeMCPExecutor:
    """记录 Registry 注入/清理时机的 fake executor。"""

    def __init__(self):
        self.current_registry = None
        self.registry_history = []

    def set_mcp_registry(self, registry):
        self.current_registry = registry
        self.registry_history.append(registry)


class FakeAsyncRegistry:
    """用于验证 async with 生命周期。"""

    def __init__(self):
        self.entered = False
        self.exited = False
        self.exit_error = None

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.exited = True
        self.exit_error = exc
        return False


class FakePipelineWithRegistry(FakePipeline):
    def __init__(self, mcp_executor):
        super().__init__()
        self.mcp_executor = mcp_executor
        self.registry_during_run = None

    async def run(
        self, task, context=None, stream_callback=None, step_callback=None
    ):
        self.registry_during_run = self.mcp_executor.current_registry
        return await super().run(
            task,
            context=context,
            stream_callback=stream_callback,
            step_callback=step_callback,
        )


class FailingPipelineWithRegistry(FakePipelineWithRegistry):
    async def run(
        self, task, context=None, stream_callback=None, step_callback=None
    ):
        self.registry_during_run = self.mcp_executor.current_registry
        raise RuntimeError("pipeline failed")


class TestRuntime(unittest.TestCase):
    def _make_runtime(self, simple_route=False, chat=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        if chat is None:
            chat = FakeChat()
        return Runtime(
            chat=chat,
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

    def test_session_context_uses_chat_summarize_messages(self):
        chat = FakeChat()
        runtime = self._make_runtime(simple_route=False, chat=chat)
        runtime.run_task("先看文件")
        runtime.run_task("修改文件")
        context = runtime.pipeline.last_context
        self.assertIn("摘要：先看文件 -> 最终结论", context["session_history"])
        self.assertIsNotNone(chat.summarized)
        roles = [m["role"] for m in chat.summarized]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)

    def test_step_callback_forwarded_to_pipeline(self):
        runtime = self._make_runtime(simple_route=False)
        steps = []
        runtime.run_task("知识库问答", step_callback=lambda s, c: steps.append((s, c)))
        self.assertIn("verify_pass", [s for s, _ in steps])

    def test_fast_path_emits_step(self):
        runtime = self._make_runtime(simple_route=True)
        steps = []
        runtime.run_task("保存文件", step_callback=lambda s, c: steps.append((s, c)))
        self.assertEqual(steps, [("fast", "快速通道：直接执行工具任务")])

    def test_pipeline_route_uses_task_scoped_mcp_registry(self):
        mcp_executor = FakeMCPExecutor()
        pipeline = FakePipelineWithRegistry(mcp_executor)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        runtime = Runtime(
            chat=FakeChat(),
            agent=FakeAgent(),
            pipeline=pipeline,
            is_simple_tool_task=lambda task: False,
            session_dir=tmp.name,
            mcp_config_path="C:/tmp/custom-mcp.json",
            mcp_executor=mcp_executor,
        )
        registry = FakeAsyncRegistry()

        with patch("vibechatbot.runtime.MCPRegistry.from_config", return_value=registry) as factory:
            result = runtime.run_task("联网查询资料")

        self.assertEqual(result["route"], "pipeline")
        factory.assert_called_once_with("C:/tmp/custom-mcp.json")
        self.assertIs(pipeline.registry_during_run, registry)
        self.assertTrue(registry.entered)
        self.assertTrue(registry.exited)
        self.assertEqual(mcp_executor.registry_history, [registry, None])
        self.assertIsNone(mcp_executor.current_registry)

    def test_pipeline_route_clears_mcp_registry_after_error(self):
        mcp_executor = FakeMCPExecutor()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        runtime = Runtime(
            chat=FakeChat(),
            agent=FakeAgent(),
            pipeline=FailingPipelineWithRegistry(mcp_executor),
            is_simple_tool_task=lambda task: False,
            session_dir=tmp.name,
            mcp_config_path="C:/tmp/custom-mcp.json",
            mcp_executor=mcp_executor,
        )
        registry = FakeAsyncRegistry()

        with patch("vibechatbot.runtime.MCPRegistry.from_config", return_value=registry):
            with self.assertRaises(RuntimeError):
                runtime.run_task("联网查询资料")

        self.assertTrue(registry.entered)
        self.assertTrue(registry.exited)
        self.assertIsInstance(registry.exit_error, RuntimeError)
        self.assertEqual(mcp_executor.registry_history, [registry, None])
        self.assertIsNone(mcp_executor.current_registry)

    def test_build_runtime_injects_executor_and_default_mcp_config(self):
        sentinel_chat = object()
        sentinel_agent = object()
        sentinel_rewriter = object()
        sentinel_executor = FakeMCPExecutor()
        sentinel_verifier = object()

        class FakePipelineCtor:
            def __init__(self, agents, verifier=None, max_retries=None):
                self.agents = agents
                self.verifier = verifier
                self.max_retries = max_retries

        with patch("vibechatbot.runtime.Chat", return_value=sentinel_chat), patch(
            "vibechatbot.runtime.Agent", return_value=sentinel_agent
        ), patch(
            "vibechatbot.runtime.RewriterAgent", return_value=sentinel_rewriter
        ), patch(
            "vibechatbot.runtime.ExecutorAgent", return_value=sentinel_executor
        ), patch(
            "vibechatbot.runtime.VerifierAgent", return_value=sentinel_verifier
        ), patch(
            "vibechatbot.runtime.Pipeline", side_effect=FakePipelineCtor
        ), patch(
            "vibechatbot.runtime.config.MCP_CONFIG", "C:/project/config/mcp.json"
        ):
            runtime = build_runtime()

        self.assertIs(runtime.chat, sentinel_chat)
        self.assertIs(runtime.agent, sentinel_agent)
        self.assertIs(runtime.mcp_executor, sentinel_executor)
        self.assertEqual(runtime.mcp_config_path, "C:/project/config/mcp.json")


if __name__ == "__main__":
    unittest.main()
