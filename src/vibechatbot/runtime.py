"""后端单例统一组装：CLI 与 Ink UI 共用同一套任务后端。

统一任务入口 run_task：简单工具任务自动走快速通道（Agent 直接执行），
其余任务走复写 → 执行 → 核查流水线。
"""

import asyncio

from vibechatbot.agent import Agent
from vibechatbot.agents import ExecutorAgent, Pipeline, RewriterAgent, VerifierAgent
from vibechatbot.agents.pipeline import is_simple_tool_task
from vibechatbot.chat import Chat


class Runtime:
    """CLI / Ink UI 共用的后端组件集合。"""

    def __init__(self, chat, agent, pipeline, is_simple_tool_task):
        self.chat = chat
        self.agent = agent
        self.pipeline = pipeline
        self.is_simple_tool_task = is_simple_tool_task

    def run_task(self, task: str) -> dict:
        """统一任务入口：简单工具任务走快速通道，其余走复写→执行→核查流水线。

        返回结构化结果：
        - 快速通道：{"route": "fast", "output": 最终回复}
        - 流水线：{"route": "pipeline", "output": 结论, "verdict": 核查判定, "attempts": 打回统计}
        """
        if self.is_simple_tool_task(task):
            return {"route": "fast", "output": self.agent.run(task) or ""}
        final = asyncio.run(self.pipeline.run(task))
        verdict = final.meta.get("verdict", {})
        return {
            "route": "pipeline",
            "output": final.meta.get("candidate", final.output),
            "verdict": verdict,
            "attempts": dict(self.pipeline.attempts),
        }


def build_runtime() -> Runtime:
    """构造聊天客户端、快速通道 Agent 与 Agentic RAG 流水线单例。"""
    chat_client = Chat()
    agent_client = Agent(chat_client)
    agentic_verifier = VerifierAgent(chat=chat_client)
    agentic_executor = ExecutorAgent(chat=chat_client)
    agentic_pipeline = Pipeline(
        [
            RewriterAgent(chat=chat_client),
            agentic_executor,
            agentic_verifier,
        ],
        verifier=agentic_verifier,
        max_retries=3,
    )
    return Runtime(
        chat=chat_client,
        agent=agent_client,
        pipeline=agentic_pipeline,
        is_simple_tool_task=is_simple_tool_task,
    )
