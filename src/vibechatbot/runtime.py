"""后端单例统一组装：CLI 与 Ink UI 共用同一套 chat/agent/agentic 后端。"""

from vibechatbot.agent import Agent
from vibechatbot.agents import ExecutorAgent, Pipeline, RewriterAgent, VerifierAgent
from vibechatbot.agents.pipeline import is_simple_tool_task
from vibechatbot.chat import Chat


class Runtime:
    """CLI / Ink UI 共用的后端组件集合。"""

    def __init__(self, chat, agent, executor, pipeline, is_simple_tool_task):
        self.chat = chat
        self.agent = agent
        self.executor = executor
        self.pipeline = pipeline
        self.is_simple_tool_task = is_simple_tool_task


def build_runtime() -> Runtime:
    """构造聊天客户端、自主 Agent 与 Agentic RAG 流水线单例。"""
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
        executor=agentic_executor,
        pipeline=agentic_pipeline,
        is_simple_tool_task=is_simple_tool_task,
    )
