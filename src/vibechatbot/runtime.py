"""后端统一组件：CLI 与 Ink UI 共用同一套任务后端。

统一任务入口 run_task：简单工具任务自动走快速通道（Agent 直接执行），
其余任务走复写 → 执行 → 核查流水线。

会话（Session）：一个终端进程 = 一个会话。会话内连续输入共享上下文
（最近几轮"任务 → 结论"注入给 agent），并统一写入同一个 JSON 存档；
重启终端即开启新会话。
"""

import asyncio
import json
import os
from datetime import datetime

from vibechatbot import config
from vibechatbot.agent import Agent
from vibechatbot.tools import file_tools
from vibechatbot.agents import ExecutorAgent, Pipeline, RewriterAgent, VerifierAgent
from vibechatbot.agents.pipeline import is_simple_tool_task
from vibechatbot.chat import Chat
from vibechatbot.mcp_registry import MCPRegistry

MAX_SESSION_ROUNDS = 5  # 注入给 agent 的最近任务轮数


class Runtime:
    """CLI / Ink UI 共用的后端组件集合（一个实例 = 一个终端会话）。"""

    def __init__(
        self,
        chat,
        agent,
        pipeline,
        is_simple_tool_task,
        session_dir: str = None,
        mcp_config_path: str = None,
        mcp_executor=None,
    ):
        self.chat = chat
        file_tools.set_memory_summarizer(
            getattr(chat, "_summarize_messages", None)
        )
        self.agent = agent
        self.pipeline = pipeline
        self.is_simple_tool_task = is_simple_tool_task
        self.session_dir = session_dir  # None 时按任务路由落到 TASK/AGENTIC 目录
        self.mcp_config_path = mcp_config_path
        self.mcp_executor = mcp_executor
        self.session_context = []  # 最近几轮 (task, output)，用于上下文注入
        self.session_records = []  # 本会话全部任务记录（写入存档）
        self.session_file = None  # 会话存档路径，首次任务时确定

    def run_task(
        self, task: str, stream_callback=None, step_callback=None
    ) -> dict:
        """统一任务入口：快速通道或复写→执行→核查，结果写入会话存档。
        step_callback: 可选，思考链步骤回调(stage, content)，供 UI 展示过程。
        """
        context = self._build_context()
        if self.is_simple_tool_task(task):
            if step_callback is not None:
                step_callback("fast", "快速通道：直接执行工具任务")
            output = self.agent.run(task, context=context) or ""
            record = {
                "route": "fast",
                "task": task,
                "messages": getattr(self.agent, "last_messages", None),
                "output": output,
            }
            result = {"route": "fast", "output": output}
        else:
            final = asyncio.run(
                self._run_pipeline_task(
                    task,
                    context=context,
                    stream_callback=stream_callback,
                    step_callback=step_callback,
                )
            )
            verdict = final.meta.get("verdict", {})
            output = final.meta.get("candidate", final.output)
            record = {
                "route": "pipeline",
                "task": task,
                "steps": getattr(self.pipeline, "last_steps", None),
                "output": output,
                "meta": final.meta,
            }
            result = {
                "route": "pipeline",
                "output": output,
                "verdict": verdict,
                "attempts": dict(self.pipeline.attempts),
            }
        self.session_records.append(record)
        self.session_context.append((task, output))
        self._save_session()
        return result

    async def _run_pipeline_task(
        self, task: str, context=None, stream_callback=None, step_callback=None
    ):
        if self.mcp_executor is None:
            return await self.pipeline.run(
                task,
                context=context,
                stream_callback=stream_callback,
                step_callback=step_callback,
            )

        registry = MCPRegistry.from_config(self.mcp_config_path or config.MCP_CONFIG)
        async with registry:
            self.mcp_executor.set_mcp_registry(registry)
            try:
                return await self.pipeline.run(
                    task,
                    context=context,
                    stream_callback=stream_callback,
                    step_callback=step_callback,
                )
            finally:
                self.mcp_executor.set_mcp_registry(None)

    def _build_context(self):
        """把最近几轮任务对话整理成上下文；无历史时返回 None。

        所有历史上下文都通过 chat._summarize_messages 做 LLM 摘要，
        不再使用字符截断。
        """
        if not self.session_context:
            return None
        messages = []
        for task, output in self.session_context[-MAX_SESSION_ROUNDS:]:
            messages.append({"role": "user", "content": f"用户: {task}"})
            messages.append({"role": "assistant", "content": f"结果: {output}"})

        summarize = getattr(self.chat, "_summarize_messages", None)
        if not callable(summarize):
            raise RuntimeError(
                "Runtime 需要 chat._summarize_messages 来生成会话上下文摘要"
            )
        summary = summarize(messages)
        return {"session_history": f"之前的对话总结：\n{summary}"}

    def _save_session(self) -> str:
        """把整个会话写入同一个 JSON：首任务创建，之后每次任务追加重写。"""
        if self.session_file is None:
            route = self.session_records[0]["route"]
            directory = self.session_dir
            if directory is None:
                directory = config.TASK_DIR if route == "fast" else config.AGENTIC_DIR
            os.makedirs(directory, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            self.session_file = os.path.join(directory, f"{timestamp}.json")
        with open(self.session_file, "w", encoding="utf-8") as file:
            json.dump(
                {"session": self.session_records},
                file,
                ensure_ascii=False,
                indent=2,
            )
        return self.session_file


def build_runtime() -> Runtime:
    """构建聊天客户端、快速通道 Agent 与 Agentic RAG 流水线单例。"""
    chat_client = Chat()
    agent_client = Agent(chat_client, save_record=False)
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
        mcp_config_path=config.MCP_CONFIG,
        mcp_executor=agentic_executor,
    )
