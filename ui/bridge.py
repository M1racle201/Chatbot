"""stdio 桥：Ink 前端通过 stdin/stdout 的 JSON 行与后端交互。

协议（每行一个 JSON 对象）：
- 命令（stdin）：{"type": "chat"|"agent"|"agentic", "content": "..."}
  {"type": "clear_history"} / {"type": "clear_memory"} / {"type": "exit"}
- 事件（stdout）：ready / user / stream / log / status / result / error / pong

依赖通过构造函数注入（chat/agent/executor/pipeline），便于单元测试。
"""

import asyncio
import contextlib
import inspect
import json
import os
import sys

# 以 ui/ 为工作目录启动时，把项目根加入模块搜索路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
# 固定工作目录为项目根，避免 VECTOR_DB/AGENTIC/CHAT 等写到 ui/ 下
os.chdir(_PROJECT_ROOT)

from agents.base import AgentMessage


def _run_sync_or_async(fn, *args):
    """执行可能是同步或异步的可调用对象（fake 与真实后端通用）。"""
    result = fn(*args)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


class _LineEmitter:
    """捕获 print 输出，按完整行转发为 log 事件。"""

    def __init__(self, emit):
        self._buffer = ""
        self._emit = emit

    def write(self, text):
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit(type="log", line=line)
        return len(text)

    def flush(self):
        if self._buffer:
            self._emit(type="log", line=self._buffer)
            self._buffer = ""


class Bridge:
    """事件转发桥：stdin 收命令，stdout 发事件。"""

    def __init__(
        self,
        chat=None,
        agent=None,
        executor=None,
        pipeline=None,
        is_simple_tool_task=None,
    ):
        self.chat = chat
        self.agent = agent
        self.executor = executor
        self.pipeline = pipeline
        self.is_simple_tool_task = is_simple_tool_task or (lambda task: False)
        self._stdout = None

    # ---------- 事件 ----------
    def _emit(self, **event):
        self._stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._stdout.flush()

    def _event_stream(self):
        """把后端 print 输出重定向为 log 事件（防止污染 JSON 协议流）。"""
        return contextlib.redirect_stdout(_LineEmitter(self._emit))

    # ---------- 主循环 ----------
    def run(self, stdin=None, stdout=None):
        """读取命令直到 /exit 或流结束。"""
        stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        # Windows 中文系统默认 GBK：强制 UTF-8，避免中文命令解析失败
        for stream in (stdin, self._stdout):
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, ValueError):
                pass
        self._emit(type="ready")
        for raw in stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                command = json.loads(line)
            except json.JSONDecodeError:
                self._emit(type="error", message=f"无法解析命令: {line[:80]}")
                continue
            if not self.handle(command):
                break

    def handle(self, command: dict) -> bool:
        """处理单条命令；返回 False 表示退出。"""
        kind = command.get("type")
        if kind == "chat":
            self._handle_chat(command.get("content", ""))
        elif kind == "agent":
            self._handle_agent(command.get("content", ""))
        elif kind == "agentic":
            self._handle_agentic(command.get("content", ""))
        elif kind == "clear_history":
            with self._event_stream():
                self.chat.history.clear()
            self._emit(type="notice", content="历史记录已清空")
        elif kind == "clear_memory":
            with self._event_stream():
                self.chat.clear_memory()
        elif kind == "ping":
            self._emit(type="pong")
        elif kind == "exit":
            return False
        else:
            self._emit(type="error", message=f"未知命令类型: {kind}")
        return True

    # ---------- 模式处理 ----------
    def _handle_chat(self, content: str) -> None:
        """聊天模式：流式转发回复块。"""
        self._emit(type="user", content=content)
        try:
            with self._event_stream():
                for chunk in self.chat.stream_chat(content):
                    self._emit(type="stream", content=chunk)
            self._emit(type="done")
        except Exception as exc:
            self._emit(type="error", message=str(exc))

    def _handle_agent(self, content: str) -> None:
        """自主任务模式：转发工具日志与过程输出。"""
        self._emit(type="user", content=content)
        self._emit(type="status", text="任务执行中...")
        try:
            with self._event_stream():
                self.agent.run(content)
            self._emit(type="status", text="任务完成")
        except Exception as exc:
            self._emit(type="error", message=str(exc))

    def _handle_agentic(self, content: str) -> None:
        """智能任务模式：快速通道或复写→执行→核查全流程。"""
        self._emit(type="user", content=content)
        try:
            if self.is_simple_tool_task(content):
                self._emit(type="status", text="快速通道：直接执行工具任务...")
                with self._event_stream():
                    final = _run_sync_or_async(
                        self.executor.run, AgentMessage(task=content)
                    )
                self._emit(type="result", content=final.output)
                return
            self._emit(type="status", text="复写 → 执行 → 核查...")
            with self._event_stream():
                final = _run_sync_or_async(self.pipeline.run, content)
            verdict = final.meta.get("verdict", {})
            conclusion = final.meta.get("candidate", final.output)
            self._emit(
                type="result",
                content=conclusion,
                verdict=verdict,
                attempts=dict(self.pipeline.attempts),
            )
        except Exception as exc:
            self._emit(type="error", message=str(exc))


def main():
    """组装真实后端并启动桥。"""
    from main import (
        agent_client,
        agentic_executor,
        agentic_pipeline,
        chat_client,
    )
    from agents.pipeline import is_simple_tool_task

    bridge = Bridge(
        chat=chat_client,
        agent=agent_client,
        executor=agentic_executor,
        pipeline=agentic_pipeline,
        is_simple_tool_task=is_simple_tool_task,
    )
    bridge.run()


if __name__ == "__main__":
    main()
