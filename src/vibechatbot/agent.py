"""自主任务 Agent：拆解任务、按需调用工具、汇报结果，并记录任务存档。"""

import json
import os
from datetime import datetime

from vibechatbot import config
from vibechatbot.tools import TOOL_DEFINITIONS, execute_tool

MAX_AGENT_STEPS = 10
TASK_DIR = config.TASK_DIR


class Agent:
    """基于 Chat 客户端的自主任务执行器。

    使用 function calling 循环：模型决定调用哪个工具 → 执行 → 结果回传，
    直到给出最终汇报；工具调用过程不输出，仅记录在 TASK JSON 存档中。
    """

    def __init__(self, chat):
        self.chat = chat

    def __init__(self, chat, save_record: bool = True):
        self.chat = chat
        self.save_record = save_record  # False 时由 Runtime 统一写会话存档
        self.last_messages = []  # 最近一次任务的消息链，供会话存档使用

    def run(self, task: str, context: dict = None) -> str:
        """执行任务：工具循环直到最终汇报；context 携带会话历史等附加上下文。"""
        agent_messages = [
            {"role": "system", "content": self.chat.system_prompt},
        ]
        history = (context or {}).get("session_history")
        if history:
            agent_messages.append({"role": "system", "content": history})
        agent_messages.append({"role": "user", "content": task})
        for _ in range(MAX_AGENT_STEPS):
            # 任务内消息按 chat.py 轮次规则管理：超限总结压缩，保留最近轮次
            agent_messages = self.chat.compress_messages(agent_messages)
            response = self.chat._create_with_retry(
                model=self.chat.model,
                messages=agent_messages,
                tools=TOOL_DEFINITIONS,
            )
            message = response.choices[0].message
            if message.tool_calls:
                message_data = message.model_dump()
                agent_messages.append(message_data)
                for tool_call in message_data["tool_calls"]:
                    name = tool_call["function"]["name"]
                    try:
                        arguments = json.loads(tool_call["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    result = execute_tool(name, arguments)
                    agent_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": result,
                        }
                    )
                continue
            reply = message.content or ""
            self.last_messages = agent_messages
            if self.save_record:
                self._save_task_record(task, agent_messages, reply)
            return reply
        print("已达最大执行步数，任务中断")
        self.last_messages = agent_messages
        if self.save_record:
            self._save_task_record(task, agent_messages, "已达最大执行步数，任务中断")
        return "已达最大执行步数，任务中断"

    def _save_task_record(self, task: str, messages: list, reply: str) -> None:
        """将任务执行记录保存为 TASK 文件夹下的 JSON 文件。"""
        os.makedirs(TASK_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = os.path.join(TASK_DIR, f"{timestamp}.json")
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(
                {"task": task, "messages": messages, "reply": reply},
                file,
                ensure_ascii=False,
                indent=2,
            )
