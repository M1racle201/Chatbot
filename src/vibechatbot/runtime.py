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
from vibechatbot.agents import ExecutorAgent, Pipeline, RewriterAgent, VerifierAgent
from vibechatbot.agents.pipeline import is_simple_tool_task
from vibechatbot.chat import Chat

MAX_SESSION_ROUNDS = 5  # 注入给 agent 的最近任务轮数
MAX_SESSION_CHARS = 2000  # 每轮结论截断长度


class Runtime:
    """CLI / Ink UI 共用的后端组件集合（一个实例 = 一个终端会话）。"""

    def __init__(
        self,
        chat,
        agent,
        pipeline,
        is_simple_tool_task,
        session_dir: str = None,
    ):
        self.chat = chat
        self.agent = agent
        self.pipeline = pipeline
        self.is_simple_tool_task = is_simple_tool_task
        self.session_dir = session_dir  # None 时按任务路由落到 TASK/AGENTIC 目录
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
                self.pipeline.run(
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

    def _build_context(self):
        """把最近几轮任务对话整理成上下文；无历史时返回 None。"""
        if not self.session_context:
            return None
        parts = ["之前的对话："]
        for task, output in self.session_context[-MAX_SESSION_ROUNDS:]:
            parts.append(f"用户: {task}\n结果: {output[:MAX_SESSION_CHARS]}")
        return {"session_history": "\n\n".join(parts)}

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
    )
