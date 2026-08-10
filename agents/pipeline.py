"""编排器:按顺序调度 Agent 链,并将全过程写入 AGENTIC 存档目录。

指定 verifier(核查器)后启用重试闭环:核查不通过 → 生成修正提示
放入 context["revision"] → 从第一个 Agent(复写器)重新执行,最多重试 max_retries 轮。
"""

import json
import os
from datetime import datetime

from agents.base import AgentMessage, BaseAgent


class Pipeline:
    """顺序执行 agent 列表,每个 agent 的输出消息传给下一个。"""

    def __init__(
        self,
        agents: list,
        max_retries: int = 3,
        archive_dir: str = "AGENTIC",
        verifier=None,
    ):
        self.agents = agents
        self.max_retries = max_retries  # 核查不通过时的最大重试轮数
        self.archive_dir = archive_dir
        self.verifier = verifier  # 核查器(须在 agents 中);None 时无闭环
        self.attempts = {"rewrite": 0, "research": 0}  # 各打回类型计数

    async def run(self, task: str) -> AgentMessage:
        """执行整条流水线;核查不通过时重试闭环,返回最终 AgentMessage。"""
        message = AgentMessage(task=task)
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
                        "meta": message.meta,
                    }
                )
            if self.verifier is None:
                break
            verdict = message.meta.get("verdict")
            if verdict is None or verdict.get("passed"):
                break
            action = verdict.get("action", "rewrite")
            self.attempts[action] = self.attempts.get(action, 0) + 1
            if self.attempts[action] > self.max_retries:
                verdict["exhausted"] = True
                break
            attempt += 1
            message.output = ""
            label = "复写打回" if action == "rewrite" else "检索打回"
            message.context["revision"] = (
                f"【{label}】{verdict.get('suggestion', '请修正后重新回答')}"
            )
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
