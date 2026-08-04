"""自主任务 Agent：拆解任务、按需调用工具、汇报结果，并记录任务存档。"""

import json
import os
from datetime import datetime

from TOOLS import TOOL_DEFINITIONS, execute_tool

MAX_AGENT_STEPS = 10
AGENT_MAX_MESSAGES = 60
TASK_DIR = "TASK"


class Agent:
    """基于 Chat 客户端的自主任务执行器。

    使用 function calling 循环：模型决定调用哪个工具 → 执行 → 结果回传，
    直到给出最终汇报；任务上下文超长时自动总结并保留最近完整消息。
    """

    def __init__(self, chat, agent_max_messages: int = AGENT_MAX_MESSAGES):
        self.chat = chat
        self.agent_max_messages = agent_max_messages

    def run(self, task: str) -> None:
        """执行任务：工具循环直到最终汇报，并把任务记录存入 TASK 文件夹。"""
        agent_messages = self.chat.messages + [{"role": "user", "content": task}]
        print("任务已接收，开始执行...")
        for _ in range(MAX_AGENT_STEPS):
            # 上下文超长时先总结压缩（保留完整消息，不断开 tool 关联）
            if len(agent_messages) > self.agent_max_messages:
                agent_messages = self._compress_agent_messages(agent_messages)
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
                    print(f"  -> 调用工具 {name}: {arguments}")
                    result = execute_tool(name, arguments)
                    print(f"    工具结果: {result}")
                    agent_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": result,
                        }
                    )
                continue
            reply = message.content or ""
            for char in reply:
                print(char, end="", flush=True)
            print()
            self._save_task_record(task, agent_messages, reply)
            return
        print("已达最大执行步数，任务中断")
        self._save_task_record(task, agent_messages, "已达最大执行步数，任务中断")

    def _compress_agent_messages(self, agent_messages: list) -> list:
        """agent 上下文超长时：总结进度，保留最近完整消息（避免截断 tool 关联）。"""
        summary = self.chat._summarize_messages(agent_messages)
        keep = agent_messages[-(self.chat.keep_recent_rounds * 2):]
        # 保留段必须从 assistant 消息开始，防止 tool 消息孤立
        start = next(
            (index for index, message in enumerate(keep)
             if message.get("role") == "assistant"),
            0,
        )
        keep = keep[start:]
        print(f"任务上下文超过 {self.agent_max_messages} 条，已总结进度并保留最近 {len(keep)} 条")
        return [
            {"role": "system", "content": self.chat.system_prompt},
            {"role": "system", "content": "任务进度总结：" + summary},
        ] + keep

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
