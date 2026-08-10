"""Agent3 核查器:检查执行结论的质量,输出通过/不通过判定与修正建议。

判定结果写入 message.meta["verdict"]:
  {"passed": bool, "reason": str, "suggestion": str}
llm 约定:可调用对象,接收 messages 列表,返回核查 JSON 文本;
支持同步函数与异步协程。"""
import inspect
import json
import os
import re

from vibechatbot import config
from vibechatbot.agents.base import AgentMessage, BaseAgent

DEFAULT_VERIFIER_PROMPT_FILE = os.path.join(config.PROMPT_DIR, "verifier")

DEFAULT_VERIFIER_PROMPT = """你是结论核查器。核查执行结果是否合格。

对照要求(最重要):
- 结论中的每个关键断言(数字、专有名词、结论性语句)优先在"检索原文"中找对应片段
- 以检索原文为准:原文是依据来源,你的常识可能基于过时的训练数据
- 结论与原文一致但与你的常识冲突 → 视为合格,不要用常识否定原文
- 常识仅作辅助:用于判断逻辑合理性与原文未覆盖的细节,不用于推翻原文
- 原文中找不到依据的关键断言 → 不通过,并在 suggestion 中指出是哪条断言无依据
- 若未提供检索原文,则凭完整性与逻辑一致性判断

不通过时,判断打回类型(action 字段):
- "rewrite":复写或表述不佳导致的理解偏差,重新表述即可解决
- "research":检索原文中缺少结论所需数据(向量库未命中或确实没有),需要换关键词重新检索
- 通过时 action 为 "pass"

只输出一个 JSON 对象,不要输出其他内容:
{"passed": true或false, "action": "pass"/"rewrite"/"research", "reason": "简短理由", "suggestion": "不通过时的修改建议,供复写器重写使用"}"""


class VerifierAgent(BaseAgent):
    """核查 message.output(结论)相对 message.task(原问题)是否合格。"""

    def __init__(
        self,
        name: str = "verifier",
        chat=None,
        llm=None,
        prompt_file: str = DEFAULT_VERIFIER_PROMPT_FILE,
    ):
        super().__init__(name=name, chat=chat)
        if llm is None and chat is None:
            raise ValueError("必须提供 llm 或 chat 之一")
        self.llm = llm
        self.prompt_file = prompt_file
        self.verifier_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """读取 prompt/verifier 作为核查提示词;文件缺失时用内置默认提示词。"""
        try:
            with open(self.prompt_file, encoding="utf-8") as file:
                content = file.read().strip()
            return content or DEFAULT_VERIFIER_PROMPT
        except OSError:
            return DEFAULT_VERIFIER_PROMPT

    async def _process(self, message: AgentMessage) -> str:
        message.meta["candidate"] = message.output  # 被核查的结论,供最终输出
        verdict = await self._verify(
            message.task, message.output, message.context.get("evidence")
        )
        message.meta["verdict"] = verdict
        if verdict["passed"]:
            return f"核查通过:{verdict.get('reason', '')}"
        return f"核查未通过:{verdict.get('reason', '')}"

    async def _verify(self, task: str, conclusion: str, evidence: list = None) -> dict:
        """调用 LLM 核查,返回结构化判定;有检索原文时要求逐条对照。"""
        user_content = f"用户问题:{task}\n\n执行结论:\n{conclusion}"
        if evidence:
            parts = [
                f"{index}. 来源《{item.get('source')}》:{item.get('content')}"
                for index, item in enumerate(evidence, 1)
            ]
            user_content += "\n\n检索原文(结论必须逐条对照以下原文,不得凭常识判断):\n" + "\n".join(parts)
        messages = [
            {"role": "system", "content": self.verifier_prompt},
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
        return self._parse_verdict(result)

    def _parse_verdict(self, raw: str) -> dict:
        """解析核查 JSON;容忍 ```json 围栏,解析失败视为不通过。"""
        text = str(raw).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            data = json.loads(text)
            passed = bool(data.get("passed"))
            action = data.get("action", "pass" if passed else "rewrite")
            if action not in ("pass", "rewrite", "research"):
                action = "pass" if passed else "rewrite"
            return {
                "passed": passed,
                "action": action,
                "reason": str(data.get("reason", "")),
                "suggestion": str(data.get("suggestion", "")),
            }
        except (json.JSONDecodeError, AttributeError):
            return {
                "passed": False,
                "action": "rewrite",
                "reason": "核查结果解析失败",
                "suggestion": "请重新复写并修正上述问题",
            }
