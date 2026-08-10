"""VerifierAgent(Agent3 核查器)单元测试。"""

import asyncio
import unittest

from agents.base import AgentMessage
from agents.verifier import VerifierAgent


class JsonLLM:
    """固定返回预设 JSON 文本,并记录收到的 messages。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return self.payload


class TestVerifierAgent(unittest.TestCase):
    def test_passed_verdict(self):
        llm = JsonLLM('{"passed": true, "reason": "有依据", "suggestion": ""}')
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(
            agent.run(AgentMessage(task="问题", output="结论"))
        )
        self.assertTrue(message.meta["verdict"]["passed"])
        self.assertEqual(message.meta["verdict"]["reason"], "有依据")
        self.assertIn("通过", message.output)

    def test_failed_verdict(self):
        llm = JsonLLM(
            '{"passed": false, "reason": "无依据", "suggestion": "补充检索"}'
        )
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(
            agent.run(AgentMessage(task="问题", output="结论"))
        )
        self.assertFalse(message.meta["verdict"]["passed"])
        self.assertEqual(message.meta["verdict"]["suggestion"], "补充检索")
        self.assertIn("未通过", message.output)

    def test_json_fence_tolerated(self):
        llm = JsonLLM('```json\n{"passed": true, "reason": "ok", "suggestion": ""}\n```')
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(agent.run(AgentMessage(task="t", output="c")))
        self.assertTrue(message.meta["verdict"]["passed"])

    def test_garbage_returns_failed(self):
        llm = JsonLLM("这根本不是 JSON")
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(agent.run(AgentMessage(task="t", output="c")))
        self.assertFalse(message.meta["verdict"]["passed"])
        self.assertEqual(message.meta["verdict"]["reason"], "核查结果解析失败")

    def test_messages_structure(self):
        llm = JsonLLM('{"passed": true, "reason": "", "suggestion": ""}')
        agent = VerifierAgent(llm=llm)
        asyncio.run(agent.run(AgentMessage(task="用户问题", output="执行结论")))
        sent = llm.calls[0]
        self.assertEqual(sent[0]["role"], "system")
        self.assertIn("用户问题", sent[1]["content"])
        self.assertIn("执行结论", sent[1]["content"])

    def test_evidence_included_in_messages(self):
        """有检索原文时,核查请求应包含原文与来源,供逐条对照。"""
        llm = JsonLLM('{"passed": true, "reason": "", "suggestion": ""}')
        agent = VerifierAgent(llm=llm)
        message = AgentMessage(task="问题", output="结论")
        message.context["evidence"] = [
            {"source": "a.pdf", "content": "原文片段一"},
            {"source": "b.docx", "content": "原文片段二"},
        ]
        asyncio.run(agent.run(message))
        sent = llm.calls[0][1]["content"]
        self.assertIn("a.pdf", sent)
        self.assertIn("原文片段一", sent)
        self.assertIn("b.docx", sent)

    def test_no_evidence_still_works(self):
        """无检索原文时按完整性与逻辑一致性判断,不报错。"""
        llm = JsonLLM('{"passed": true, "reason": "ok", "suggestion": ""}')
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(
            agent.run(AgentMessage(task="问题", output="结论"))
        )
        self.assertTrue(message.meta["verdict"]["passed"])

    def test_action_research_parsed(self):
        llm = JsonLLM('{"passed": false, "action": "research", "reason": "无数据", "suggestion": "换词检索"}')
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(agent.run(AgentMessage(task="t", output="c")))
        self.assertEqual(message.meta["verdict"]["action"], "research")

    def test_action_defaults_to_rewrite(self):
        """不通过且未提供 action 时,默认按复写打回处理。"""
        llm = JsonLLM('{"passed": false, "reason": "无依据", "suggestion": "改"}')
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(agent.run(AgentMessage(task="t", output="c")))
        self.assertEqual(message.meta["verdict"]["action"], "rewrite")

    def test_action_pass_when_passed(self):
        llm = JsonLLM('{"passed": true, "reason": "ok", "suggestion": ""}')
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(agent.run(AgentMessage(task="t", output="c")))
        self.assertEqual(message.meta["verdict"]["action"], "pass")

    def test_candidate_recorded(self):
        """被核查的结论应存入 meta["candidate"],供最终输出使用。"""
        llm = JsonLLM('{"passed": true, "reason": "ok", "suggestion": ""}')
        agent = VerifierAgent(llm=llm)
        message = asyncio.run(
            agent.run(AgentMessage(task="问题", output="候选结论"))
        )
        self.assertEqual(message.meta["candidate"], "候选结论")

    def test_no_llm_and_no_chat_raises(self):
        with self.assertRaises(ValueError):
            VerifierAgent()


if __name__ == "__main__":
    unittest.main()
