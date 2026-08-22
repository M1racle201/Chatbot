"""编排器:按顺序调度 Agent 链,并将全过程写入 AGENTIC 存档目录。

指定 verifier(核查器)后启用重试闭环:核查不通过 → 生成修正提示
放入 context["revision"] → 从第一个 Agent(复写器)重新执行,最多重试 max_retries 轮。
"""

import json
import os
from datetime import datetime

from jobmatchagent import config
from jobmatchagent.agents.base import AgentMessage, BaseAgent


class Pipeline:
    """顺序执行 agent 列表,每个 agent 的输出消息传给下一个。"""

    def __init__(
        self,
        agents: list,
        max_retries: int = 3,
        archive_dir: str = None,
        verifier=None,
    ):
        self.agents = agents
        self.max_retries = max_retries  # 核查不通过时的最大重试轮数
        self.archive_dir = archive_dir  # None 时不写存档,由 Runtime 统一会话存档
        self.verifier = verifier  # 核查器(须在 agents 中);None 时无闭环
        self.attempts = {"rewrite": 0, "research": 0}  # 各打回类型计数
        self.last_steps = []  # 最近一次任务的步骤记录,供会话存档使用

    async def run(
        self, task: str, context: dict = None, stream_callback=None,
        step_callback=None,
    ) -> AgentMessage:
        """执行整条流水线;核查不通过时重试闭环,返回最终 AgentMessage。

        context: 可选的共享上下文(如会话历史),作为 AgentMessage.context 初值。
        stream_callback: 可选,把各 agent 的流式文本增量转发(如 UI 实时显示)。
        step_callback: 可选,思考链步骤回调(stage, content),供 UI 展示过程。
        """
        for agent in self.agents:
            agent.stream_callback = stream_callback
            agent.step_callback = step_callback
        message = AgentMessage(task=task, context=dict(context or {}))
        steps = []
        attempt = 0
        self.attempts = {"rewrite": 0, "research": 0}  # 任务级计数,每次执行重置
        while True:
            for agent in self.agents:
                message = await agent.run(message)
                steps.append(
                    {
                        "attempt": attempt,
                        "agent": agent.name,
                        "output": message.output,
                        "meta": {
                            **message.meta,
                            "process_log": list(message.meta.get("process_log", [])),
                        },
                    }
                )
                if step_callback is not None and agent.name == "rewriter":
                    step_callback(
                        "rewriter", f"复写后任务: {message.output[:120]}"
                    )
            if self.verifier is None:
                break
            verdict = message.meta.get("verdict")
            if verdict is None or verdict.get("passed"):
                if step_callback is not None:
                    step_callback("verify_pass", "核查通过")
                break
            action = verdict.get("action", "rewrite")
            self.attempts[action] = self.attempts.get(action, 0) + 1
            if self.attempts[action] > self.max_retries:
                verdict["exhausted"] = True
                break
            attempt += 1
            message.output = ""
            label = "复写打回" if action == "rewrite" else "检索打回"
            if step_callback is not None:
                reason = verdict.get("reason") or verdict.get("suggestion") or "请修正"
                step_callback(
                    "verify_reject", f"核查打回({label}): {reason[:120]}"
                )
                step_callback("retry", f"第 {attempt} 轮重试")
            message.context["revision"] = (
                f"【{label}】{verdict.get('suggestion', '请修正后重新回答')}"
            )
        self.last_steps = steps
        if self.archive_dir is not None:
            self._archive(task, steps, message.output, message.meta)
        return message

    def _archive(self, task: str, steps: list, output: str, meta: dict = None) -> str:
        """将流水线过程写入 AGENTIC/时间戳.json,返回文件路径。"""
        os.makedirs(self.archive_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = os.path.join(self.archive_dir, f"{timestamp}.json")
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "task": task,
                    "steps": steps,
                    "output": output,
                    "meta": meta,
                },
                file,
                ensure_ascii=False,
                indent=2,
            )
        return filename


# 简单工具任务快速通道：不涉及知识库推理，直接由执行器完成，跳过复写/核查
_SIMPLE_TOOL_KEYWORDS = (
    "读取", "读文件", "保存", "生成", "写入", "输出",
    "load", "save_file", "add_documents", "入库",
)


def is_simple_tool_task(task: str) -> bool:
    """判断任务是否为无需检索/核查的简单工具调用（快速通道）。

    启发式：命中任意简单工具关键词即判定为 True。关键词可在此处调整。
    """
    return any(keyword in task for keyword in _SIMPLE_TOOL_KEYWORDS)
