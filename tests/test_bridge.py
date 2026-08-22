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

    def __call__(self, task, stream_callback=None, step_callback=None):
        if task == "保存文件":
            return {"route": "fast", "output": "快速通道结论"}
        return {
            "route": "pipeline",
            "output": "最终结论",
            "verdict": {"passed": False, "reason": "缺少依据", "exhausted": True},
            "attempts": {"rewrite": 1, "research": 2},
        }


class FakeStreamRunTask:
    """带流式回调的 fake：任务执行中逐块输出文本。"""

    def __call__(self, task, stream_callback=None, step_callback=None):
        if stream_callback:
            stream_callback("chunk-a"); stream_callback("chunk-b")
        return {"route": "fast", "output": "done"}


class FakeStepRunTask:
    """带思考链回调的 fake：执行中上报复写与核查步骤。"""

    def __call__(self, task, stream_callback=None, step_callback=None):
        if step_callback:
            step_callback("rewriter", "复写后任务: 检查文件")
            step_callback("tool", "load(x.pdf)", tool="load")
            step_callback("tool_result", "{\"content\": \"ok\"}", tool="load")
            step_callback("verify_pass", "核查通过")
        return {"route": "pipeline", "output": "done"}


def run_bridge(commands, run_task=None, apply_settings=None):
    stdin = io.StringIO(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in commands) + "\n"
    )
    stdout = io.StringIO()
    bridge = Bridge(
        chat=FakeChat(),
        run_task=run_task or FakeRunTask(),
        apply_settings=apply_settings,
    )
    bridge.run(stdin=stdin, stdout=stdout)
    return [json.loads(line) for line in stdout.getvalue().strip().splitlines()]


class TestBridge(unittest.TestCase):
    def test_ready_on_start(self):
        events = run_bridge([])
        self.assertEqual(events, [{"type": "ready", "model": "", "base_url": ""}])

    def test_task_fast_path_emits_result(self):
        events = run_bridge([{"type": "task", "content": "保存文件"}])
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "快速通道结论")
        self.assertEqual(results[0]["route"], "fast")
        self.assertIs(results[0]["streamed"], False)  # 快速通道不流式

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
        self.assertEqual(lines[0], {"type": "ready", "model": "", "base_url": ""})
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

    def test_task_stream_chunks_forwarded(self):
        events = run_bridge(
            [{"type": "task", "content": "save file"}], run_task=FakeStreamRunTask()
        )
        streams = [e for e in events if e["type"] == "stream"]
        self.assertEqual([e["content"] for e in streams], ["chunk-a", "chunk-b"])
        results = [e for e in events if e["type"] == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "done")
        self.assertIs(results[0]["streamed"], True)  # 发过流式文本

    def test_task_steps_forwarded(self):
        events = run_bridge(
            [{"type": "task", "content": "x"}], run_task=FakeStepRunTask()
        )
        steps = [e for e in events if e["type"] == "step"]
        self.assertEqual(
            [s["stage"] for s in steps],
            ["rewriter", "tool", "tool_result", "verify_pass"],
        )
        self.assertEqual(steps[0]["content"], "复写后任务: 检查文件")
        self.assertEqual(steps[1]["tool"], "load")
        self.assertEqual(steps[2]["tool"], "load")

    def test_settings_command_emits_sanitized_success(self):
        received = []

        def apply_settings(settings):
            received.append(settings)
            return {"model": settings["model"]}

        events = run_bridge(
            [
                {
                    "type": "settings",
                    "settings": {
                        "base_url": "https://example.com/v1",
                        "api_key": "secret-key",
                        "model": "model-x",
                    },
                }
            ],
            apply_settings=apply_settings,
        )
        result = [e for e in events if e["type"] == "settings_result"][0]
        self.assertEqual(result, {"type": "settings_result", "ok": True, "content": "配置已生效", "model": "model-x"})
        self.assertEqual(received[0]["api_key"], "secret-key")
        self.assertNotIn("secret-key", json.dumps(events, ensure_ascii=False))

    def test_settings_command_emits_failure_without_secret(self):
        def apply_settings(settings):
            raise ValueError("API URL 无效")

        events = run_bridge(
            [
                {
                    "type": "settings",
                    "settings": {
                        "base_url": "bad-url",
                        "api_key": "secret-key",
                        "model": "model-x",
                    },
                }
            ],
            apply_settings=apply_settings,
        )
        result = [e for e in events if e["type"] == "settings_result"][0]
        self.assertEqual(
            result,
            {"type": "settings_result", "ok": False, "content": "API URL 无效"},
        )
        self.assertNotIn("secret-key", json.dumps(events, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
