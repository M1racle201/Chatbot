"""stdio 桥：Ink 前端通过 stdin/stdout 的 JSON 行与后端交互。

协议（每行一个 JSON 对象）：
- 命令（stdin）：{"type": "task", "content": "..."}
  兼容别名：{"type": "agent"} / {"type": "agentic"}（统一按 task 处理）
  {"type": "clear_history"} / {"type": "clear_memory"} / {"type": "exit"}
- 事件（stdout）：ready / user / stream / log / status / result / error / pong

依赖通过构造函数注入（chat/run_task），便于单元测试。
"""

import asyncio
import contextlib
import inspect
import json
import sys

from vibechatbot.runtime import build_runtime


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

    def __init__(self, chat=None, run_task=None):
        self.chat = chat
        self.run_task = run_task or (lambda content: {"route": "fast", "output": ""})
        self._stdout = None
        self._streamed = False  # 当前任务是否发过流式文本（UI 据此避免结果重复显示）

    # ---------- 事件 ----------
    def _emit(self, **event):
        self._stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._stdout.flush()

    def emit_stream(self, content: str) -> None:
        """把 agent 的流式文本增量转发为 stream 事件（供前端实时显示）。"""
        self._emit(type="stream", content=content)
        self._streamed = True

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
        self._emit(type="ready", model=getattr(self.chat, "model", ""))
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
        if kind in ("task", "agent", "agentic"):
            self._handle_task(command.get("content", ""))
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

    # ---------- 统一任务处理 ----------
    def _handle_task(self, content: str) -> None:
        """统一任务模式：快速通道或复写→执行→核查，结果以 result 事件返回。"""
        self._emit(type="user", content=content)
        self._streamed = False  # 每个任务独立统计是否产生流式文本
        self._emit(type="status", text="任务执行中...")
        try:
            with self._event_stream():
                result = _run_sync_or_async(
                    self.run_task, content, self.emit_stream
                )
            self._emit(
                type="result",
                content=result.get("output", ""),
                route=result.get("route", "pipeline"),
                verdict=result.get("verdict", {}),
                attempts=result.get("attempts", {}),
                streamed=self._streamed,
            )
        except Exception as exc:
            self._emit(type="error", message=str(exc))


def main():
    """组装真实后端并启动桥。"""
    runtime = build_runtime()
    bridge = Bridge(chat=runtime.chat, run_task=runtime.run_task)
    bridge.run()


if __name__ == "__main__":
    main()
