"""ui/bridge.py stdio 协议单元测试(注入 fake 后端,不联网)。"""

import io
import json
import unittest

from agents.base import AgentMessage
from ui.bridge import Bridge


class FakeHistory:
    def clear(self):
        print("历史记录已清空")


class FakeChat:
    def __init__(self):
        self.history = FakeHistory()

    def stream_chat(self, content):
        print("已导入 2 条历史记录")
        yield "你"
        yield "好"

    def clear_memory(self):
        print("对话记忆已清除")


class FakeAgent:
    def run(self, task):
        print("  → load(...) => ok")
        print("任务完成汇报")


class FakeExecutor:
    def run(self, message):
        return AgentMessage(task=message.task, output="快速通道结论")


class FakePipeline:
    def __init__(self):
        self.attempts = {"rewrite": 1, "research": 2}

    def run(self, task):
        return AgentMessage(
            task=task,
            output="候选结论",
            meta={
                "verdict": {
                    "passed": False,
                    "reason": "缺少依据",
                    "exhausted": True,
                },
                "candidate": "最终结论",
            },
        )


def run_bridge(commands, is_simple=None):
    stdin = io.StringIO(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in commands) + "\n"
    )
    stdout = io.StringIO()
    bridge = Bridge(
        chat=FakeChat(),
        agent=FakeAgent(),
        executor=FakeExecutor(),
        pipeline=FakePipeline(),
        is_simple_tool_task=is_simple or (lambda task: False),
    )
    bridge.run(stdin=stdin, stdout=stdout)
    return [json.loads(line) for line in stdout.getvalue().strip().splitlines()]


class TestBridge(unittest.TestCase):
    def test_ready_on_start(self):
        events = run_bridge([])
        self.assertEqual(events, [{"type": "ready"}])

    def test_chat_streams_and_done(self):
        events = run_bridge([{"type": "chat", "content": "你好"}])
        kinds = [e["type"] for e in events]
        self.assertIn("user", kinds)
        self.assertIn("stream", kinds)
        self.assertEqual(events[-1], {"type": "done"})
        stream_text = "".join(e["content"] for e in events if e["type"] == "stream")
        self.assertEqual(stream_text, "你好")

    def test_chat_captures_print_as_log(self):
        events = run_bridge([{"type": "chat", "content": "你好"}])
        log_lines = [e["line"] for e in events if e["type"] == "log"]
        self.assertIn("已导入 2 条历史记录", log_lines)

    def test_agent_emits_logs_and_status(self):
        events = run_bridge([{"type": "agent", "content": "总结报告"}])
        kinds = [e["type"] for e in events]
        self.assertIn("status", kinds)
        log_lines = [e["line"] for e in events if e["type"] == "log"]
        self.assertIn("  → load(...) => ok", log_lines)
        self.assertIn("任务完成汇报", log_lines)

    def test_agentic_fast_path(self):
        events = run_bridge(
            [{"type": "agentic", "content": "保存文件"}],
            is_simple=lambda task: True,
        )
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "快速通道结论")

    def test_agentic_full_flow(self):
        events = run_bridge([{"type": "agentic", "content": "知识库问答"}])
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "最终结论")
        self.assertEqual(results[0]["verdict"]["exhausted"], True)
        self.assertEqual(results[0]["attempts"], {"rewrite": 1, "research": 2})

    def test_clear_history_and_memory(self):
        events = run_bridge([{"type": "clear_history"}, {"type": "clear_memory"}])
        log_lines = [e["line"] for e in events if e["type"] == "log"]
        self.assertIn("历史记录已清空", log_lines)
        self.assertIn("对话记忆已清除", log_lines)

    def test_bad_json_returns_error(self):
        events = run_bridge([])
        stdin = io.StringIO("not-json\n")
        stdout = io.StringIO()
        bridge = Bridge(chat=FakeChat(), agent=FakeAgent())
        bridge.run(stdin=stdin, stdout=stdout)
        lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
        self.assertEqual(lines[0], {"type": "ready"})
        errors = [e for e in lines if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("无法解析命令", errors[0]["message"])

    def test_unknown_command_returns_error(self):
        events = run_bridge([{"type": "fly"}])
        errors = [e for e in events if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("未知命令类型", errors[0]["message"])

    def test_exit_stops_loop(self):
        events = run_bridge([{"type": "exit"}, {"type": "chat", "content": "x"}])
        kinds = [e["type"] for e in events]
        self.assertNotIn("user", kinds)


if __name__ == "__main__":
    unittest.main()
