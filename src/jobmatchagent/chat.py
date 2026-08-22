"""DeepSeek 聊天客户端：封装聊天 API 调用与消息管理。"""

import time

from openai import (
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from jobmatchagent.config import BASE_URL, DEEPSEEK_API, HISTORY_FILE, MODEL_DEFAULT, PROMPT_FILE
from jobmatchagent.history import History

MAX_ROUNDS = 60
KEEP_RECENT_ROUNDS = 20
MAX_RETRIES = 3
RETRY_DELAY = 5


class Chat:
    """基于 DeepSeek API 的聊天客户端。

    messages 结构：[system 提示词] + [{"role": "user", "content": 用户输入}] ...
    聊天记录保存在 CHAT 文件夹。
    对话轮次超过 MAX_ROUNDS 时，总结全部对话并只保留最近 KEEP_RECENT_ROUNDS 轮。
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
                self._reset_retry_dedup()  # 新流从头比对，跳过已发送前缀
                self._wait_and_report(exc, attempt)
        return None

    def _dedup(self, new: str, sent: str, offset: int):
        """跳过 new 中与已发送文本 sent 重叠的前缀（重试重发时去重）。

        返回 (增量文本, 更新后的已发送文本, 新的匹配偏移)。
        """
        if offset < len(sent):
            remaining = sent[offset:]
            if remaining.startswith(new):
                return "", sent, offset + len(new)
            if new.startswith(remaining):
                return new[len(remaining):], sent, len(sent)
            return new, sent, len(sent)  # 输出与旧文本不一致，停止跳过
        return new, sent + new, len(sent) + len(new)

    def _skip_duplicate(self, chunk) -> None:
        """重试重发时跳过已发送过的文本/工具调用增量（原地修改 chunk）。"""
        if not chunk.choices:
            return
        delta = chunk.choices[0].delta
        if delta.content:
            delta.content, self._sent_text, self._sent_offset = self._dedup(
                delta.content, self._sent_text, self._sent_offset
            )
        for call in delta.tool_calls or []:
            parts = self._sent_calls.setdefault(
                call.index,
                {"name": "", "name_off": 0, "args": "", "args_off": 0},
            )
            if call.function is None:
                continue
            if call.function.name:
                call.function.name, parts["name"], parts["name_off"] = self._dedup(
                    call.function.name, parts["name"], parts["name_off"]
                )
            if call.function.arguments:
                call.function.arguments, parts["args"], parts["args_off"] = self._dedup(
                    call.function.arguments, parts["args"], parts["args_off"]
                )

    def _stream_with_retry(self, **kwargs):
        """流式请求：迭代过程中遇 429/5xx/超时自动重试。"""
        # 重试去重状态：重试重发时跳过已发送过的文本/工具调用前缀
        self._sent_text = ""
        self._sent_offset = 0
        self._sent_calls = {}
        for attempt in range(self.max_retries + 1):
            try:
                stream = self.client.chat.completions.create(**kwargs)
                for chunk in stream:
                    self._skip_duplicate(chunk)
                    yield chunk
                return
            except (RateLimitError, InternalServerError, APITimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise
                self._wait_and_report(exc, attempt)
                self._reset_retry_dedup()  # 新流从头比对，跳过已发送前缀

    def _reset_retry_dedup(self) -> None:
        """重试重发前重置匹配偏移：新流从头比对已发送文本。"""
        self._sent_offset = 0
        for parts in self._sent_calls.values():
            parts["name_off"] = 0
            parts["args_off"] = 0

    def stream_completion(
        self,
        messages: list,
        tools: list = None,
        on_chunk=None,
    ) -> tuple:
        """流式请求：逐块回调文本增量，聚合完整文本与工具调用。

        返回 (content, tool_calls)：content 为完整回复文本；tool_calls 为
        聚合后的工具调用列表（与 model_dump 的 tool_calls 结构一致），无则为空列表。
        """
        stream = self._stream_with_retry(
            model=self.model, messages=messages, tools=tools, stream=True
        )

        content_parts = []
        tool_calls = {}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                if on_chunk:
                    on_chunk(delta.content)
            for call in delta.tool_calls or []:
                entry = tool_calls.setdefault(
                    call.index,
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if call.id:
                    entry["id"] = call.id
                if call.function:
                    if call.function.name:
                        entry["function"]["name"] += call.function.name
                    if call.function.arguments:
                        entry["function"]["arguments"] += call.function.arguments
        ordered = [tool_calls[index] for index in sorted(tool_calls)]
        return "".join(content_parts), ordered

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

    def compress_messages(
        self,
        messages: list,
        max_rounds: int = None,
        keep_recent_rounds: int = None,
    ) -> list:
        """按 chat.py 的轮次规则压缩消息列表（供任务内复用）。

        超过 max_rounds 轮时：总结全部消息，保留 system 提示词 + 总结 +
        最近 keep_recent_rounds 轮；压缩结果从 assistant 消息开始截取，
        避免 tool 消息孤立。不写盘，任务结束即弃。
        """
        max_rounds = self.max_rounds if max_rounds is None else max_rounds
        keep_recent_rounds = (
            self.keep_recent_rounds
            if keep_recent_rounds is None
            else keep_recent_rounds
        )
        rounds = sum(1 for m in messages if m.get("role") != "system") // 2
        if rounds <= max_rounds:
            return messages
        summary = self._summarize_messages(messages)
        compressed = self.history.compress(
            messages, summary, keep_recent_rounds=keep_recent_rounds
        )
        # 保留段可能从 tool 消息开头（其 assistant 被截掉），跳过孤立 tool，
        # 避免 API 校验失败；system 前缀（提示词 + 总结）保留
        prefix_end = 0
        while prefix_end < len(compressed) and compressed[prefix_end].get("role") == "system":
            prefix_end += 1
        tool_end = prefix_end
        while tool_end < len(compressed) and compressed[tool_end].get("role") == "tool":
            tool_end += 1
        if tool_end > prefix_end:
            return compressed[:prefix_end] + compressed[tool_end:]
        return compressed

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

    def clear_memory(self) -> None:
        """清除对话记忆：仅重置内存中的 messages，不清空历史文件。"""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        print("对话记忆已清除")
