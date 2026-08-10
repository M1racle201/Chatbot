from pathlib import Path
import unittest


UI_SOURCE = (Path(__file__).parents[1] / "ui" / "index.jsx").read_text(
    encoding="utf-8"
)


class TestInkUiLayout(unittest.TestCase):
    def test_focused_thread_shell_has_separate_regions(self):
        for marker in (
            "function Header(",
            "function Transcript(",
            "function Message(",
            "function Composer(",
            "function useTerminalSize(",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, UI_SOURCE)

    def test_primary_messages_wrap_and_use_semantic_prompts(self):
        self.assertIn("wrap=\"wrap\"", UI_SOURCE)
        self.assertIn("{'› '}", UI_SOURCE)
        self.assertIn("{'AI  '}", UI_SOURCE)
        self.assertIn("RESERVED_SHELL_ROWS", UI_SOURCE)


if __name__ == "__main__":
    unittest.main()
