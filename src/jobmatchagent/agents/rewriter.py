"""Agent1 复写器:将用户输入复写为清晰、完整、适合语义检索的表述。

llm 为可调用对象:接收 messages 列表,返回回复文本。
支持同步函数与异步协程函数(自动 await)。
真实运行时传入 chat 客户端适配函数,测试时注入 mock。
"""

import inspect
import os

from jobmatchagent import config
from jobmatchagent.agents.base import AgentMessage, BaseAgent

DEFAULT_REWRITE_PROMPT_FILE = os.path.join(config.PROMPT_DIR, "rewriter")

DEFAULT_REWRITE_PROMPT = """你是表达复写器。任务:把用户的输入复写为清晰、完整、适合语义检索的表述。

要求:
- 保持原意,不改变用户意图,不添加知识库之外的事实
- 补全口语化的省略和指代(如"这个""它""那个文档"),使表述完整
- 提取核心问题,使复写结果适合直接用于知识库检索
- 如果用户输入本身已清晰完整,原样输出
- 如果收到"上一轮核查反馈",注意前缀:
  - 【复写打回】:上一轮表述不佳,重新组织语言,保持原意但更清晰完整
  - 【检索打回】:检索未命中,调整表述(同义词、更宽泛或更具体),帮助检索到知识库内容;若知识库确实没有,如实说明
- 只输出复写后的文本,不要解释、不要加任何前缀或引号"""


class RewriterAgent(BaseAgent):
    """将 message.task 交给 LLM 复写,结果写入 message.output。"""

    def __init__(
        self,
        name: str = "rewriter",
        chat=None,
        llm=None,
        prompt_file: str = DEFAULT_REWRITE_PROMPT_FILE,
    ):
        super().__init__(name=name, chat=chat)
        if llm is None and chat is None:
            raise ValueError("必须提供 llm 或 chat 之一")
        self.llm = llm
        self.prompt_file = prompt_file
        self.rewrite_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """读取 prompt/rewriter 作为复写提示词;文件缺失时用内置默认提示词。"""
        try:
            with open(self.prompt_file, encoding="utf-8") as file:
                content = file.read().strip()
            return content or DEFAULT_REWRITE_PROMPT
        except OSError:
            return DEFAULT_REWRITE_PROMPT

    async def _process(self, message: AgentMessage) -> str:
        user_content = message.task
        history = message.context.get("session_history")
        if history:
            user_content = f"{history}\n\n当前任务: {message.task}"
        revision = message.context.get("revision")
        if revision:
            user_content = f"{user_content}\n\n上一轮核查反馈:{revision}"
        messages = [
            {"role": "system", "content": self.rewrite_prompt},
            {"role": "user", "content": user_content},
        ]
        if self.llm is not None:
            result = self.llm(messages)
        else:
            response = self.chat._create_with_retry(
                model=self.chat.model, messages=messages
            )
            result = response.choices[0].message.content or ""
        if inspect.isawaitable(result):
            result = await result
        return result.strip()
