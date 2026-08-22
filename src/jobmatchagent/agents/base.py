"""Agent 基座:AgentMessage 通信载体 + BaseAgent 异步抽象基类。

所有 Agent(复写/执行/核查)都继承 BaseAgent,只需实现 _process():
  输入 AgentMessage → 返回输出文本(自动写入 message.output)。
run() 统一负责过程日志、耗时统计与异常记录,子类不需要关心。
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentMessage:
    """Agent 之间传递的统一消息结构。"""

    task: str  # 本轮任务/用户输入
    context: dict = field(default_factory=dict)  # 共享上下文(检索结果、附加信息等)
    output: str = ""  # 本 agent 的输出文本
    meta: dict = field(default_factory=dict)  # 元信息(agent 名、过程日志、耗时等)


class BaseAgent:
    """异步 Agent 抽象基类。

    子类必须实现 async _process(message) -> str;
    run() 会包装:写入过程日志、统计耗时、异常时记录错误并重新抛出。
    """

    def __init__(self, name: str, chat=None):
        self.name = name
        self.chat = chat  # Chat 客户端(LLM 调用),基座阶段可为 None
        self.stream_callback = None  # 可选:流式文本增量回调(如转发给 UI)
        self.step_callback = None  # 可选:思考链步骤回调(如转发给 UI 展示)
        self.last_message: Optional[AgentMessage] = None

    async def run(self, message: AgentMessage) -> AgentMessage:
        """执行一次处理:记录日志与耗时,返回填充了 output 的消息。"""
        self.last_message = message
        log = message.meta.setdefault("process_log", [])
        log.append({"agent": self.name, "event": "start", "task": message.task})
        message.meta["agent"] = self.name
        started = time.perf_counter()
        try:
            message.output = await self._process(message)
        except Exception as exc:
            log.append({"agent": self.name, "event": "error", "error": str(exc)})
            message.meta["error"] = str(exc)
            raise
        finally:
            message.meta["elapsed_ms"] = round(
                (time.perf_counter() - started) * 1000, 2
            )
        log.append({"agent": self.name, "event": "end"})
        return message

    async def _process(self, message: AgentMessage) -> str:
        """子类实现:处理输入消息,返回输出文本。"""
        raise NotImplementedError(
            f"{type(self).__name__} 必须实现 async _process(message)"
        )
