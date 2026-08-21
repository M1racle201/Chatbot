"""Pipeline 编排器单元测试。"""

import asyncio
import json
import os
import tempfile
import unittest

from vibechatbot.agents.base import AgentMessage, BaseAgent
from vibechatbot.agents.pipeline import Pipeline, is_simple_tool_task


class EchoAgent(BaseAgent):
    """按顺序拼接前缀,验证上一个 agent 的输出会传给下一个。"""

    def __init__(self, name: str, prefix: str = ""):
        super().__init__(name=name)
        self.prefix = prefix
        self.calls = []

    async def _process(self, message: AgentMessage) -> str:
        base = message.output or message.task
        self.calls.append(base)
        return self.prefix + base + "|"


class FakeRewriter(BaseAgent):
    """重试时带修正反馈的复写器。"""

    def __init__(self, name="rewriter"):
        super().__init__(name=name)
        self.revisions = []

    async def _process(self, message: AgentMessage) -> str:
        self.revisions.append(message.context.get("revision"))
        if message.context.get("revision"):
            return "复写:" + message.task + "[修正]"
        return "复写:" + message.task


class FakeExecutor(BaseAgent):
    """读取上一个 agent 的输出作为输入。"""

    def __init__(self, name="executor"):
        super().__init__(name=name)

    async def _process(self, message: AgentMessage) -> str:
        return "结论:" + (message.output or message.task)


class FakeVerifier(BaseAgent):
    """按预设结果序列返回核查判定。"""

    def __init__(self, results, name="verifier"):
        super().__init__(name=name)
        self.results = list(results)
        self.rounds = 0

    async def _process(self, message: AgentMessage) -> str:
        self.rounds += 1
        item = self.results.pop(0) if self.results else True
        if isinstance(item, bool):
            passed, action = item, "rewrite"
        else:
            passed = item.get("passed", True)
            action = item.get("action", "rewrite")
        message.meta["verdict"] = {
            "passed": passed,
            "action": action,
            "reason": "reason",
            "suggestion": "修正建议",
        }
        return "核查通过" if passed else "核查未通过"


class TestPipelineRetryLoop(unittest.TestCase):
    def test_retry_until_passed(self):
        verifier = FakeVerifier([False, False, True])
        pipeline = Pipeline(
            [FakeRewriter(), FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=3,
        )
        final = asyncio.run(pipeline.run("任务"))
        self.assertTrue(final.meta["verdict"]["passed"])
        self.assertEqual(verifier.rounds, 3)  # 两次不通过后第三次通过
        self.assertNotIn("exhausted", final.meta["verdict"])

    def test_revision_fed_back_to_rewriter(self):
        verifier = FakeVerifier([False, True])
        rewriter = FakeRewriter()
        pipeline = Pipeline(
            [rewriter, FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=3,
        )
        final = asyncio.run(pipeline.run("任务"))
        self.assertTrue(final.meta["verdict"]["passed"])
        # 复写器第一轮无反馈,第二轮收到带类型的打回建议
        self.assertEqual(rewriter.revisions, [None, "【复写打回】修正建议"])

    def test_retry_exhausted(self):
        verifier = FakeVerifier([False, False, False, False, False])
        pipeline = Pipeline(
            [FakeRewriter(), FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=2,  # 允许 2 次重试,共 3 轮尝试
        )
        final = asyncio.run(pipeline.run("任务"))
        self.assertTrue(final.meta["verdict"]["exhausted"])
        self.assertEqual(verifier.rounds, 3)

    def test_rewrite_and_research_counts(self):
        """rewrite 与 research 分别计数,并最终通过。"""
        verifier = FakeVerifier(
            [
                {"passed": False, "action": "rewrite"},
                {"passed": False, "action": "research"},
                {"passed": True, "action": "pass"},
            ]
        )
        pipeline = Pipeline(
            [FakeRewriter(), FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=3,
        )
        final = asyncio.run(pipeline.run("任务"))
        self.assertTrue(final.meta["verdict"]["passed"])
        self.assertEqual(pipeline.attempts, {"rewrite": 1, "research": 1})
        self.assertEqual(verifier.rounds, 3)

    def test_research_exhausted_separately(self):
        """research 单独达上限即强制输出,不因 rewrite 未用而放宽。"""
        verifier = FakeVerifier(
            [{"passed": False, "action": "research"}] * 5
        )
        pipeline = Pipeline(
            [FakeRewriter(), FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=2,
        )
        final = asyncio.run(pipeline.run("任务"))
        self.assertTrue(final.meta["verdict"]["exhausted"])
        self.assertEqual(pipeline.attempts, {"rewrite": 0, "research": 3})
        self.assertEqual(verifier.rounds, 3)

    def test_revision_prefix_by_action(self):
        """打回原因带类型标记:复写打回 / 检索打回。"""
        verifier = FakeVerifier(
            [
                {"passed": False, "action": "rewrite"},
                {"passed": False, "action": "research"},
                {"passed": True, "action": "pass"},
            ]
        )
        rewriter = FakeRewriter()
        pipeline = Pipeline(
            [rewriter, FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=3,
        )
        asyncio.run(pipeline.run("任务"))
        self.assertEqual(
            rewriter.revisions,
            [None, "【复写打回】修正建议", "【检索打回】修正建议"],
        )

    def test_attempts_reset_between_runs(self):
        """每次 run 重新计数,任务间不累积。"""
        verifier = FakeVerifier(
            [{"passed": False, "action": "research"}, {"passed": True, "action": "pass"}]
        )
        pipeline = Pipeline(
            [FakeRewriter(), FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=3,
        )
        asyncio.run(pipeline.run("任务1"))
        self.assertEqual(pipeline.attempts, {"rewrite": 0, "research": 1})
        verifier.results = [True]  # 第二个任务一次通过
        asyncio.run(pipeline.run("任务2"))
        self.assertEqual(pipeline.attempts, {"rewrite": 0, "research": 0})

    def test_pass_first_try(self):
        verifier = FakeVerifier([True])
        pipeline = Pipeline(
            [FakeRewriter(), FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=3,
        )
        final = asyncio.run(pipeline.run("任务"))
        self.assertTrue(final.meta["verdict"]["passed"])
        self.assertEqual(verifier.rounds, 1)

    def test_step_callback_emits_chain(self):
        """思考链事件：复写 → 打回 → 重试 → 核查通过。"""
        verifier = FakeVerifier([False, True])
        pipeline = Pipeline(
            [FakeRewriter(), FakeExecutor(), verifier],
            verifier=verifier,
            max_retries=3,
        )
        steps = []
        asyncio.run(
            pipeline.run("任务", step_callback=lambda s, c: steps.append((s, c)))
        )
        stages = [s for s, _ in steps]
        self.assertEqual(stages[0], "rewriter")
        self.assertIn("verify_reject", stages)
        self.assertIn("retry", stages)
        self.assertIn("verify_pass", stages)
        self.assertEqual(steps[-1][0], "verify_pass")


class TestEvidenceFlow(unittest.TestCase):
    def test_evidence_flows_to_verifier(self):
        """执行器写入的检索原文应传递到核查器。"""

        class EvidenceExecutor(BaseAgent):
            def __init__(self):
                super().__init__(name="executor")

            async def _process(self, message: AgentMessage) -> str:
                message.context["evidence"] = [
                    {"source": "a.pdf", "content": "片段"}
                ]
                return "结论"

        class CheckVerifier(BaseAgent):
            def __init__(self):
                super().__init__(name="verifier")
                self.seen = None

            async def _process(self, message: AgentMessage) -> str:
                self.seen = message.context.get("evidence")
                message.meta["verdict"] = {"passed": True, "reason": "", "suggestion": ""}
                return "ok"
                self.seen = message.context.get("evidence")
                message.meta["verdict"] = {"passed": True, "reason": "", "suggestion": ""}
                return "ok"

        verifier = CheckVerifier()
        pipeline = Pipeline([EvidenceExecutor(), verifier], verifier=verifier)
        asyncio.run(pipeline.run("任务"))
        self.assertEqual(verifier.seen, [{"source": "a.pdf", "content": "片段"}])


class TestPipeline(unittest.TestCase):
    def test_sequential_execution(self):
        agents = [
            EchoAgent("a1", "1:"),
            EchoAgent("a2", "2:"),
            EchoAgent("a3", "3:"),
        ]
        pipeline = Pipeline(agents)
        final = asyncio.run(pipeline.run("任务"))
        self.assertEqual(final.output, "3:2:1:任务|||")
        # 每个 agent 的输入是上一个的输出
        self.assertEqual(agents[1].calls[0], "1:任务|")
        self.assertEqual(agents[2].calls[0], "2:1:任务||")

    def test_archive_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents = [EchoAgent("a1", "1:"), EchoAgent("a2", "2:")]
            pipeline = Pipeline(agents, archive_dir=tmp)
            asyncio.run(pipeline.run("hello"))

            files = os.listdir(tmp)
            self.assertEqual(len(files), 1)
            with open(os.path.join(tmp, files[0]), encoding="utf-8") as file:
                data = json.load(file)
            self.assertEqual(data["task"], "hello")
            self.assertEqual(len(data["steps"]), 2)
            self.assertEqual(data["steps"][0]["agent"], "a1")
            self.assertEqual(data["steps"][0]["output"], "1:hello|")
            self.assertEqual(data["steps"][1]["agent"], "a2")
            # 每个步骤应记录自己的 meta，而不是共享最后一个 agent 的 meta
            self.assertEqual(data["steps"][0]["meta"]["agent"], "a1")
            self.assertEqual(data["steps"][1]["meta"]["agent"], "a2")
            self.assertEqual(data["output"], "2:1:hello||")

    def test_error_propagates(self):
        class Boom(BaseAgent):
            async def _process(self, message: AgentMessage) -> str:
                raise RuntimeError("bad")

        pipeline = Pipeline([EchoAgent("a1"), Boom("a2")])
        with self.assertRaises(RuntimeError):
            asyncio.run(pipeline.run("x"))


class TestIsSimpleToolTask(unittest.TestCase):
    def test_simple_tool_keywords_return_true(self):
        for task in ("读取 C:/a.pdf 并保存", "生成报告并输出到文件", "把 D:/x.docx 入库"):
            with self.subTest(task=task):
                self.assertTrue(is_simple_tool_task(task))

    def test_knowledge_reasoning_returns_false(self):
        self.assertFalse(is_simple_tool_task("基于知识库回答深海采矿的影响"))

    def test_browser_and_search_tasks_stay_on_general_mcp_path(self):
        self.assertFalse(is_simple_tool_task("打开网页并总结内容"))
        self.assertFalse(is_simple_tool_task("搜索在线资料并比较结果"))
        self.assertFalse(is_simple_tool_task("browse this website and report findings"))
        self.assertTrue(is_simple_tool_task("保存这段文本到文件"))


if __name__ == "__main__":
    unittest.main()
