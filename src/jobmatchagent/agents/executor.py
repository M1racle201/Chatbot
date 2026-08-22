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

from jobmatchagent import config
from jobmatchagent.agents.base import AgentMessage, BaseAgent

MAX_EXECUTOR_STEPS = 10
MAX_TOOL_RESULT_STEP_CHARS = 1600  # UI 思考链中单个工具结果最多展示的字符数
CONVERGENCE_ROUNDS = 2  # 连续 N 轮输出相似视为收敛
SIMILARITY_THRESHOLD = 0.98  # 快照相似度阈值(微调参数不视为收敛,完全相同才收敛)
MAX_EXECUTOR_MESSAGES = 60
KEEP_RECENT_MESSAGES = 40
MAX_EVIDENCE_ITEMS = 3  # 传给核查器的依据片段上限
MAX_EVIDENCE_CHARS = 500  # 每段依据片段截断长度
DEFAULT_EXECUTOR_PROMPT_FILE = os.path.join(config.PROMPT_DIR, "executor")

DEFAULT_EXECUTOR_PROMPT = """你是主题执行器,负责基于向量知识库与工具完成用户任务。

流程规范:
- 涉及知识库内容的问题,先调用 query_documents 检索,再基于检索结果回答
- 向量库为空时,明确告知用户先上传/入库数据,停止知识库回答,不要扫描文件系统兜底
- 回答时标注信息来源文件名(如:根据《xxx.pdf》)
- 检索结果不足时明确说明"知识库中没有相关内容",不要猜测
- 读取文件用 load,文档入库用 add_documents,简短输出用 save_file
- 论文、代码、HTML、长报告等长文本一律用 save_long_output 保存到 OUTPUT 目录
- 长文本保存后只向终端回复文件路径和大小,禁止直接粘贴大段正文
- 仅当用户明确要求源码/原文/完整内容时才允许把长文本直接输出到终端
- write_file 可写任意路径(自动创建父目录),但严禁写入向量库目录(VECTOR_DB)
- 每完成一轮与用户的对话后,用 remember_conversation 保存该轮任务与结论的简略总结
- 当用户询问"之前说过什么/上下文/上次对话"等上下文问题时,先调用 query_memory 检索记忆再回答
- 完成时输出最终结论,不要输出过程描述

# 技能调用规范
- 知识库检索按 kb-retriever 技能:query_documents 先命中子文档,再自动返回对应父文档上下文
- 每次调用 run_python_script 前，必须先按 security-best-practices 技能检查脚本；命中高危规则禁止执行，不得用混淆绕过
- 所有面向用户的回复默认按 output-format 技能排版；长文本用 save_long_output 保存，终端只回文件路径和大小
- 你可以调用 [iterative-retrieval]、[kb-retriever]、[output-format]、[security-best-practices] 来帮助你完成任务
- 技能清单(名称 → 说明文件路径):
  - kb-retriever → skills/kb-retriever/SKILL.md
  - iterative-retrieval → skills/iterative-retrieval/SKILL.md
  - output-format → skills/output-format/SKILL.md
  - security-best-practices → skills/security-best-practices/SKILL.md
- 调用方式:先用 load 读取对应技能的 SKILL.md,再严格按其中的描述与步骤执行"""


def _tool_result_step_text(result: str, limit: int = MAX_TOOL_RESULT_STEP_CHARS) -> str:
    """生成适合 UI 思考链展示的工具结果文本。

    - 把常见工具结果转成可直接换行阅读的文本，避免 UI 收到一整行带 \\n 转义的 JSON
    - 超长时保留头尾两段，省略中间，保证末尾的统计信息/退出码不会被截掉
    """
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        text = result
    else:
        if isinstance(data, dict) and isinstance(data.get("stdout"), str):
            parts = [data["stdout"].rstrip()]
            if data.get("stderr"):
                parts.append("stderr:\n" + data["stderr"].rstrip())
            if "exit_code" in data:
                parts.append(f"exit_code: {data['exit_code']}")
            text = "\n".join(parts)
        elif isinstance(data, dict) and isinstance(data.get("content"), str):
            prefix = f"path: {data['path']}\n" if data.get("path") else ""
            text = prefix + data["content"]
        elif isinstance(data, dict) and isinstance(data.get("results"), list):
            lines = []
            for index, item in enumerate(data["results"], 1):
                source = item.get("source") or "unknown"
                content = item.get("content") or ""
                lines.append(f"{index}. 《{source}》 {content}")
            text = "\n".join(lines) or json.dumps(data, ensure_ascii=False, indent=2)
        else:
            text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    prefix_size = max(1, (limit - 40) // 2)
    suffix_size = max(1, limit - 40 - prefix_size)
    return (
        text[:prefix_size]
        + f"\n… 中间省略 {omitted} 字符 …\n"
        + text[-suffix_size:]
    )


def _default_tools():
    """加载工具定义(真实运行时;避免测试环境依赖 chromadb)。"""
    from jobmatchagent.tools import TOOL_DEFINITIONS

    return TOOL_DEFINITIONS


def _default_tool_executor():
    from jobmatchagent.tools import execute_tool

    return execute_tool


class _StreamReply:
    """流式聚合后的回复对象：兼容 response.choices[0].message 的接口。"""

    def __init__(self, content: str, tool_calls: list):
        self.content = content
        self.tool_calls = tool_calls

    @property
    def choices(self) -> list:
        """Simulate response.choices[0].message access path."""
        choice = type("Choice", (), {"message": self})()
        return [choice]

    def model_dump(self) -> dict:
        return {
            "role": "assistant",
            "content": self.content or None,
            "tool_calls": self.tool_calls,
        }


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
            if self.stream_callback is not None:
                # 执行器是唯一向用户输出结论的 agent，最终结论才需要流式
                content, tool_calls = self.chat.stream_completion(
                    messages, tools=self.tools, on_chunk=self.stream_callback
                )
                result = _StreamReply(content, tool_calls or None)
            else:
                result = self.chat._create_with_retry(
                    model=self.chat.model, messages=messages, tools=self.tools
                )
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _process(self, message: AgentMessage) -> str:
        agent_messages = [{"role": "system", "content": self.executor_prompt}]
        history = message.context.get("session_history")
        if history:
            agent_messages.append({"role": "system", "content": history})
        agent_messages.append(
            {"role": "user", "content": message.output or message.task}
        )
        snapshots = []
        evidence = []
        for _ in range(self.max_steps):
            if self.chat is not None:
                # 真实运行时：任务内消息按 chat.py 轮次规则管理
                agent_messages = self.chat.compress_messages(agent_messages)
            elif len(agent_messages) > self.max_messages:
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
                    if self.step_callback is not None:
                        arg_text = json.dumps(arguments, ensure_ascii=False)[:100]
                        self.step_callback(
                            "tool", f"{name}({arg_text})", tool=name
                        )
                    result = await asyncio.to_thread(
                        self.tool_executor, name, arguments
                    )
                    if self.step_callback is not None:
                        self.step_callback(
                            "tool_result",
                            _tool_result_step_text(result),
                            tool=name,
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
        """把收集到的依据片段写入共享上下文,供核查器对照。

        无条件覆盖:即使本轮未采集到依据(如仅用了 run_python_script 等
        非检索工具),也要清掉上一轮遗留的旧 evidence,避免核查器拿过期原文对照。
        """
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
