"""DeepSeek 聊天客户端：封装 API 调用与消息管理。"""

import json
import os
import time
from datetime import datetime

from openai import (
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from config import BASE_URL, DEEPSEEK_API, MODEL_DEFAULT, PROMPT_FILE
from history import HISTORY_FILE, History
from TOOLS import TOOL_DEFINITIONS, execute_tool

MAX_ROUNDS = 60
KEEP_RECENT_ROUNDS = 20
MAX_AGENT_STEPS = 10
MAX_RETRIES = 3
RETRY_DELAY = 5
AGENT_MAX_MESSAGES = 60
TASK_DIR = "TASK"


class Chat:
    """基于 DeepSeek API 的聊天客户端。

    messages 结构：[system 提示词] + [{"role": "user", "content": 用户输入}] ...
    聊天记录保存在 CHAT 文件夹，任务记录保存在 TASK 文件夹。
    对话轮次超过 MAX_ROUNDS 时，总结全部对话并只保留最近 KEEP_RECENT_ROUNDS 轮。
    agent 任务消息超过 AGENT_MAX_MESSAGES 条时，总结进度并保留最近完整消息。
    请求遇 429/5xx/超时会自动等待重试。
    """

    def __init__(
        self,
        api_key: str = DEEPSEEK_API,
        base_url: str = BASE_URL,
        model: str = MODEL_DEFAULT,
        history_file: str = HISTORY_FILE,
        max_rounds: int = MAX_ROUNDS,
        keep_recent_rounds: int = KEEP_RECENT_ROUNDS,
        max_retries: int = MAX_RETRIES,
        retry_delay: int = RETRY_DELAY,
        agent_max_messages: int = AGENT_MAX_MESSAGES,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.system_prompt = self._load_system_prompt()
        self.history = History(history_file)
        self.max_rounds = max_rounds
        self.keep_recent_rounds = keep_recent_rounds
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.agent_max_messages = agent_max_messages
        # 首次打开终端聊天时加载历史；history.json 有内容则导入
        loaded = self.history.load()
        self.loaded_count = len(loaded)
        self.messages = self._ensure_system_prompt(loaded)
        self._notified = False

    def _load_system_prompt(self) -> str:
        """读取 prompt/system 文件作为系统提示词。"""
        try:
            with open(PROMPT_FILE, encoding="utf-8") as file:
                return file.read().strip()
        except OSError:
            return ""

    def _ensure_system_prompt(self, messages: list) -> list:
        """保证历史消息以 system 提示词开头。"""
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": self.system_prompt}] + messages
        return messages

    def _wait_and_report(self, exc: Exception, attempt: int) -> None:
        """打印重试提示并等待。"""
        wait = self.retry_delay * (attempt + 1)
        print(f"\nAPI 繁忙（{getattr(exc, 'status_code', 'unknown')}），"
              f"{wait} 秒后重试（{attempt + 1}/{self.max_retries}）...")
        time.sleep(wait)

    def _create_with_retry(self, **kwargs):
        """非流式请求：遇 429/5xx/超时自动重试。"""
        for attempt in range(self.max_retries + 1):
            try:
                return self.client.chat.completions.create(**kwargs)
            except (RateLimitError, InternalServerError, APITimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise
                self._wait_and_report(exc, attempt)
        return None

    def _stream_with_retry(self, **kwargs):
        """流式请求：迭代过程中遇 429/5xx/超时自动重试。"""
        for attempt in range(self.max_retries + 1):
            try:
                stream = self.client.chat.completions.create(**kwargs)
                yield from stream
                return
            except (RateLimitError, InternalServerError, APITimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise
                self._wait_and_report(exc, attempt)

    def _summarize_messages(self, messages: list) -> str:
        """调用模型简略总结给定消息列表。"""
        response = self._create_with_retry(
            model=self.model,
            messages=messages
            + [{"role": "user", "content": "请用简洁的语言总结以上内容。"}],
        )
        return response.choices[0].message.content or ""

    def _summarize(self) -> str:
        """调用模型简略总结全部对话。"""
        return self._summarize_messages(self.messages)

    def _check_length(self) -> bool:
        """对话轮次超过上限时总结并压缩历史；返回是否发生了压缩。"""
        rounds = sum(1 for m in self.messages if m.get("role") != "system") // 2
        if rounds > self.max_rounds:
            summary = self._summarize()
            self.messages = self.history.compress(
                self.messages, summary, keep_recent_rounds=self.keep_recent_rounds
            )
            self.history.save(self.messages)
            print(f"对话轮次超过 {self.max_rounds}，已总结并保留最近 {self.keep_recent_rounds} 轮")
            return True
        return False

    def _compress_agent_messages(self, agent_messages: list) -> list:
        """agent 上下文超长时：总结进度，保留最近完整消息（避免截断 tool 关联）。"""
        summary = self._summarize_messages(agent_messages)
        keep = agent_messages[-(self.keep_recent_rounds * 2):]
        # 保留段必须从 assistant 消息开始，防止 tool 消息孤立
        start = next(
            (index for index, message in enumerate(keep)
             if message.get("role") == "assistant"),
            0,
        )
        keep = keep[start:]
        print(f"任务上下文超过 {self.agent_max_messages} 条，已总结进度并保留最近 {len(keep)} 条")
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": "任务进度总结：" + summary},
        ] + keep

    def chat(self, user_input: str) -> None:
        """基础聊天：流式打印回复到终端，不直接返回整段文字。"""
        self._notify_loaded_history()
        for chunk in self.stream_chat(user_input):
            print(chunk, end="", flush=True)
        print()

    def _notify_loaded_history(self) -> None:
        """开启新终端聊天时，提示导入了多少条历史记录（仅提示一次）。"""
        if not self._notified:
            self._notified = True
            if self.loaded_count > 0:
                print(f"已导入 {self.loaded_count} 条历史记录")

    def stream_chat(self, user_input: str):
        """流式聊天：逐块产出回复内容（生成器函数），结束后保存历史。"""
        self.messages.append({"role": "user", "content": user_input})
        stream = self._stream_with_retry(
            model=self.model,
            messages=self.messages,
            stream=True,
        )
        chunks = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                chunks.append(content)
                yield content
        self.messages.append({"role": "assistant", "content": "".join(chunks)})
        if not self._check_length():
            self.history.save(self.messages)

    def agent_chat(self, task: str) -> None:
        """自主任务模式：按需调用工具，直到给出最终汇报，并把任务记录存入 TASK 文件夹。"""
        agent_messages = self.messages + [{"role": "user", "content": task}]
        print("任务已接收，开始执行...")
        for _ in range(MAX_AGENT_STEPS):
            # 上下文超长时先总结压缩（保留完整消息，不断开 tool 关联）
            if len(agent_messages) > self.agent_max_messages:
                agent_messages = self._compress_agent_messages(agent_messages)
            response = self._create_with_retry(
                model=self.model,
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

    def clear_memory(self) -> None:
        """清除对话记忆：仅重置内存中的 messages，不清空历史文件。"""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        print("对话记忆已清除")
