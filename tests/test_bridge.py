"""src/vibechatbot/bridge.py stdio 协议单元测试（注入 fake 后端，不联网）。"""

import io
import json
import unittest

from vibechatbot.bridge import Bridge


class FakeHistory:
    def clear(self):
        print("历史记录已清空")


class FakeChat:
    def __init__(self):
        self.history = FakeHistory()

    def clear_memory(self):
        print("对话记忆已清除")


class FakeRunTask:
    """按任务返回结构化结果的 fake 统一任务入口。"""

    def __call__(self, task):
        if task == "保存文件":
            return {"route": "fast", "output": "快速通道结论"}
        return {
            "route": "pipeline",
            "output": "最终结论",
            "verdict": {"passed": False, "reason": "缺少依据", "exhausted": True},
            "attempts": {"rewrite": 1, "research": 2},
        }


def run_bridge(commands, run_task=None):
    stdin = io.StringIO(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in commands) + "\n"
    )
    stdout = io.StringIO()
    bridge = Bridge(chat=FakeChat(), run_task=run_task or FakeRunTask())
    bridge.run(stdin=stdin, stdout=stdout)
    return [json.loads(line) for line in stdout.getvalue().strip().splitlines()]


class TestBridge(unittest.TestCase):
    def test_ready_on_start(self):
        events = run_bridge([])
        self.assertEqual(events, [{"type": "ready"}])

    def test_task_fast_path_emits_result(self):
        events = run_bridge([{"type": "task", "content": "保存文件"}])
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "快速通道结论")
        self.assertEqual(results[0]["route"], "fast")

    def test_task_full_flow_emits_verdict_and_attempts(self):
        events = run_bridge([{"type": "task", "content": "知识库问答"}])
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "最终结论")
        self.assertEqual(results[0]["route"], "pipeline")
        self.assertEqual(results[0]["verdict"]["exhausted"], True)
        self.assertEqual(results[0]["attempts"], {"rewrite": 1, "research": 2})

    def test_agent_alias_routes_to_task(self):
        events = run_bridge([{"type": "agent", "content": "保存文件"}])
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "快速通道结论")

    def test_agentic_alias_routes_to_task(self):
        events = run_bridge([{"type": "agentic", "content": "知识库问答"}])
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "最终结论")

    def test_clear_history_and_memory(self):
        events = run_bridge([{"type": "clear_history"}, {"type": "clear_memory"}])
        log_lines = [e["line"] for e in events if e["type"] == "log"]
        self.assertIn("历史记录已清空", log_lines)
        self.assertIn("对话记忆已清除", log_lines)

    def test_bad_json_returns_error(self):
        stdin = io.StringIO("not-json\n")
        stdout = io.StringIO()
        bridge = Bridge(chat=FakeChat(), run_task=FakeRunTask())
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
        events = run_bridge([{"type": "exit"}, {"type": "task", "content": "x"}])
        kinds = [e["type"] for e in events]
        self.assertNotIn("user", kinds)


if __name__ == "__main__":
    unittest.main()
