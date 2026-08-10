"""Agent2 主题执行器:检索 + 工具调用 + 结论生成。

流程:组装消息 → 调 LLM(携带工具定义)→ 有 tool_calls 则执行工具并回传
→ 直到模型给出最终结论。上下文超长时总结进度并压缩(保留最近完整消息)。

llm 约定:可调用对象,接收 (messages, tools=None) 参数,返回 response 对象
(需支持 .choices[0].message.{tool_calls,content,model_dump()});
支持同步函数与异步协程。
tool_executor 约定:同步函数 (name, arguments) -> 结果字符串;默认 TOOLS.execute_tool。
TOOLS 在使用点延迟加载,测试环境无需安装 chromadb。
"""

import asyncio
import difflib
import inspect
import json
import os

from agents.base import AgentMessage, BaseAgent

MAX_EXECUTOR_STEPS = 10
CONVERGENCE_ROUNDS = 2  # 连续 N 轮输出相似视为收敛
SIMILARITY_THRESHOLD = 0.98  # 快照相似度阈值(微调参数不视为收敛,完全相同才收敛)
MAX_EXECUTOR_MESSAGES = 60
KEEP_RECENT_MESSAGES = 40
MAX_EVIDENCE_ITEMS = 3  # 传给核查器的依据片段上限
MAX_EVIDENCE_CHARS = 500  # 每段依据片段截断长度
DEFAULT_EXECUTOR_PROMPT_FILE = os.path.join("prompt", "executor")

DEFAULT_EXECUTOR_PROMPT = """你是主题执行器,负责基于向量知识库与工具完成用户任务。

流程规范:
- 涉及知识库内容的问题,先调用 query_documents 检索,再基于检索结果回答
- 回答时标注信息来源文件名(如:根据《xxx.pdf》)
- 检索结果不足时明确说明"知识库中没有相关内容",不要猜测
- 读取文件用 load,文档入库用 add_documents,输出文件用 save_file
- 文件只允许保存到 OUTPUT 目录,不要执行删除向量库等危险操作
- 完成时输出最终结论,不要输出过程描述"""


def _default_tools():
    """加载工具定义(真实运行时;避免测试环境依赖 chromadb)。"""
    from TOOLS import TOOL_DEFINITIONS

    return TOOL_DEFINITIONS


def _default_tool_executor():
    from TOOLS import execute_tool

    return execute_tool


class ExecutorAgent(BaseAgent):
    """根据复写后的任务,通过工具循环生成最终结论。"""

    def __init__(
        self,
        name: str = "executor",
        chat=None,
        llm=None,
        tools=None,
        tool_executor=None,
        prompt_file: str = DEFAULT_EXECUTOR_PROMPT_FILE,
        max_steps: int = MAX_EXECUTOR_STEPS,
        max_messages: int = MAX_EXECUTOR_MESSAGES,
        convergence_rounds: int = CONVERGENCE_ROUNDS,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        max_evidence_items: int = MAX_EVIDENCE_ITEMS,
        max_evidence_chars: int = MAX_EVIDENCE_CHARS,
    ):
        super().__init__(name=name, chat=chat)
        if llm is None and chat is None:
            raise ValueError("必须提供 llm 或 chat 之一")
        self.llm = llm
        self.tools = tools  # None 时在使用点延迟加载
        self.tool_executor = tool_executor  # None 时在使用点延迟加载
        self.prompt_file = prompt_file
        self.executor_prompt = self._load_prompt()
        self.max_steps = max_steps
        self.max_messages = max_messages
        self.convergence_rounds = convergence_rounds
        self.similarity_threshold = similarity_threshold
        self.max_evidence_items = max_evidence_items
        self.max_evidence_chars = max_evidence_chars

    def _load_prompt(self) -> str:
        """读取 prompt/executor 作为执行提示词;文件缺失时用内置默认提示词。"""
        try:
            with open(self.prompt_file, encoding="utf-8") as file:
                content = file.read().strip()
            return content or DEFAULT_EXECUTOR_PROMPT
        except OSError:
            return DEFAULT_EXECUTOR_PROMPT

    async def _call_llm(self, messages: list):
        """调用 LLM:优先注入的 llm,否则用 chat 客户端(带工具定义)。"""
        if self.llm is not None:
            result = self.llm(messages, tools=self.tools)
        else:
            if self.tools is None:
                self.tools = _default_tools()
            result = self.chat._create_with_retry(
                model=self.chat.model, messages=messages, tools=self.tools
            )
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _process(self, message: AgentMessage) -> str:
        agent_messages = [{"role": "system", "content": self.executor_prompt}]
        agent_messages.append(
            {"role": "user", "content": message.output or message.task}
        )
        snapshots = []
        evidence = []
        for _ in range(self.max_steps):
            if len(agent_messages) > self.max_messages:
                agent_messages = self._compress(agent_messages)
            response = await self._call_llm(agent_messages)
            reply = response.choices[0].message
            if reply.tool_calls:
                message_data = reply.model_dump()
                agent_messages.append(message_data)
                snapshots.append(self._snapshot(message_data))
                if self._is_converged(snapshots):
                    self._flush_evidence(message, evidence)
                    tool_names = [
                        tc["function"]["name"] for tc in message_data["tool_calls"]
                    ]
                    return (
                        f"执行收敛(连续 {self.convergence_rounds} 轮输出相似),"
                        f"未生成新结论;最近执行工具: {', '.join(tool_names)}"
                    )
                for tool_call in message_data["tool_calls"]:
                    if self.tool_executor is None:
                        self.tool_executor = _default_tool_executor()
                    name = tool_call["function"]["name"]
                    try:
                        arguments = json.loads(
                            tool_call["function"]["arguments"] or "{}"
                        )
                    except json.JSONDecodeError:
                        arguments = {}
                    result = await asyncio.to_thread(
                        self.tool_executor, name, arguments
                    )
                    agent_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": result,
                        }
                    )
                    self._collect_evidence(evidence, name, result)
                continue
            self._flush_evidence(message, evidence)
            return (reply.content or "").strip()
        self._flush_evidence(message, evidence)
        return "已达最大执行步数,未能生成结论"

    def _collect_evidence(self, evidence: list, tool_name: str, result: str) -> None:
        """从工具结果中收集核查依据片段(query_documents 检索结果 / load 内容)。"""
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):  # 工具可能返回数组等非对象结果
            return
        if tool_name == "query_documents":
            for item in data.get("results", []):
                if len(evidence) >= self.max_evidence_items:
                    return
                content = (item.get("content") or "")[: self.max_evidence_chars]
                if content:
                    evidence.append(
                        {"source": item.get("source"), "content": content}
                    )
        elif tool_name == "load":
            if len(evidence) >= self.max_evidence_items:
                return
            content = (data.get("content") or "")[: self.max_evidence_chars]
            if content:
                evidence.append({"source": data.get("path"), "content": content})

    def _flush_evidence(self, message: AgentMessage, evidence: list) -> None:
        """把收集到的依据片段写入共享上下文,供核查器对照。"""
        if evidence:
            message.context["evidence"] = evidence

    def _snapshot(self, message_data: dict) -> str:
        """把一轮 LLM 回复压成可比对的快照:工具调用取 工具名+参数,否则取文本内容。"""
        if message_data.get("tool_calls"):
            return "|".join(
                f'{tc["function"]["name"]}({tc["function"]["arguments"] or ""})'
                for tc in message_data["tool_calls"]
            )
        return message_data.get("content") or ""

    def _is_converged(self, snapshots: list) -> bool:
        """连续 convergence_rounds 对相邻快照相似度达标即视为收敛。"""
        if len(snapshots) < self.convergence_rounds + 1:
            return False
        window = snapshots[-(self.convergence_rounds + 1):]
        return all(
            difflib.SequenceMatcher(None, window[i], window[i - 1]).ratio()
            >= self.similarity_threshold
            for i in range(1, len(window))
        )

    def _compress(self, agent_messages: list) -> list:
        """上下文超长时:总结进度,保留最近完整消息(从 assistant 开始,不断开 tool 关联)。"""
        if self.chat is not None:
            summary = self.chat._summarize_messages(agent_messages)
        else:
            summary = "进度总结(测试环境未连接 LLM)"
        keep = agent_messages[-KEEP_RECENT_MESSAGES:]
        start = next(
            (index for index, m in enumerate(keep) if m.get("role") == "assistant"),
            0,
        )
        keep = keep[start:]
        return [
            {"role": "system", "content": self.executor_prompt},
            {"role": "system", "content": "任务进度总结:" + summary},
        ] + keep
