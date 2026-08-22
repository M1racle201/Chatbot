"""父子文档分块单元测试。"""

import unittest

from vibechatbot.chunking import (
    CHILD_CHARS,
    CHILD_OVERLAP,
    PARENT_CHARS,
    split_children,
    split_parent_children,
    split_parents,
)


class TestChunking(unittest.TestCase):
    def test_constants_are_sane(self):
        self.assertLess(CHILD_OVERLAP, CHILD_CHARS)
        self.assertLess(CHILD_CHARS, PARENT_CHARS)

    def test_split_parents_short_text(self):
        self.assertEqual(split_parents("短文本", max_chars=10), ["短文本"])

    def test_split_parents_long_text(self):
        text = "第一句内容。" * 200
        parents = split_parents(text, max_chars=100)
        self.assertGreater(len(parents), 1)
        for parent in parents:
            self.assertTrue(parent)
            self.assertLessEqual(len(parent), 110)

    def test_split_children_has_overlap(self):
        parent = "今天天气很好。明天预计下雨。后天转晴。大后天降温。周末适合出行。" * 5
        children = split_children(parent, max_chars=80, overlap=20)
        self.assertGreater(len(children), 1)
        for child in children:
            self.assertLessEqual(len(child), 90)
        for left, right in zip(children, children[1:]):
            self.assertTrue(right.startswith(left[-20:]))

    def test_split_parent_children_structure(self):
        text = "第一段内容。" * 300
        groups = split_parent_children(
            text, parent_chars=120, child_chars=60, overlap=15
        )
        self.assertGreater(len(groups), 1)
        for group in groups:
            self.assertTrue(group["parent"])
            self.assertTrue(group["children"])
            for child in group["children"]:
                self.assertLessEqual(len(child), 75)


if __name__ == "__main__":
    unittest.main()
