from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
APP_SOURCE = (ROOT / "ui" / "index.jsx").read_text(encoding="utf-8")
WORKBENCH_PATH = ROOT / "ui" / "workbench.jsx"
WORKBENCH_SOURCE = (
    WORKBENCH_PATH.read_text(encoding="utf-8") if WORKBENCH_PATH.exists() else ""
)


class TestInkUiLayout(unittest.TestCase):
    def test_workbench_has_reference_image_regions(self):
        for marker in (
            "function Sidebar(",
            "function WorkspaceHeader(",
            "function ToolActivity(",
            "function ResultPanel(",
            "function Transcript(",
            "function Composer(",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, WORKBENCH_SOURCE)

    def test_visual_copy_matches_the_approved_workbench(self):
        for copy in (
            "VibeChatbot",
            "Threads",
            "Files",
            "Tasks",
            "Recent threads",
            "Agent ready",
            "Context:",
            "Ask the agent to inspect, build, or explain...",
            "You",
            "Agent",
        ):
            with self.subTest(copy=copy):
                self.assertIn(copy, WORKBENCH_SOURCE)

    def test_app_integrates_wide_and_compact_layouts(self):
        self.assertIn("isWideLayout(columns)", APP_SOURCE)
        self.assertIn("flexGrow={1}", APP_SOURCE)
        self.assertIn("<Sidebar", APP_SOURCE)
        self.assertIn("<WorkspaceHeader", APP_SOURCE)

    def test_unified_task_mode_and_commands(self):
        for command in (
            "/clear_history",
            "/clear_memory",
            "/clear_memmory",
            "/exit",
        ):
            with self.subTest(command=command):
                self.assertIn(command, APP_SOURCE)
        self.assertIn("type: 'task'", APP_SOURCE)
        self.assertNotIn("/chat", APP_SOURCE)


if __name__ == "__main__":
    unittest.main()
