"""write_file 工具单元测试：除 VECTOR_DB 外任意路径可写。"""

import os
import tempfile
import unittest
from unittest.mock import patch

from vibechatbot import config
from vibechatbot.tools import file_tools


class TestWriteFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = os.path.join(self.tmp.name, "output")
        os.makedirs(self.output)
        self.vector_db = os.path.join(self.tmp.name, "VECTOR_DB")

    def _call(self, path, content="新内容"):
        with patch.object(file_tools, "OUTPUT_DIR", self.output), patch.object(
            config, "WRITE_DIRS", []
        ), patch.object(config, "VECTOR_DB_DIR", self.vector_db):
            return file_tools.write_file(path, content)

    def test_write_new_file_inside_output(self):
        target = os.path.join(self.output, "报告.txt")
        result = self._call(target, "你好")
        self.assertNotIn("error", result)
        self.assertFalse(result["updated"])
        with open(target, encoding="utf-8") as file:
            self.assertEqual(file.read(), "你好")

    def test_write_overwrites_existing_file(self):
        target = os.path.join(self.output, "a.txt")
        with open(target, "w", encoding="utf-8") as file:
            file.write("旧内容")
        result = self._call(target, "新内容")
        self.assertTrue(result["updated"])
        with open(target, encoding="utf-8") as file:
            self.assertEqual(file.read(), "新内容")

    def test_write_outside_whitelist_allowed(self):
        target = os.path.join(self.tmp.name, "outside.txt")
        result = self._call(target)
        self.assertNotIn("error", result)
        self.assertTrue(os.path.exists(target))

    def test_write_to_vector_db_rejected(self):
        os.makedirs(self.vector_db)
        target = os.path.join(self.vector_db, "chroma.sqlite3")
        result = self._call(target)
        self.assertIn("error", result)
        self.assertFalse(os.path.exists(target))

    def test_write_creates_parent_directories(self):
        target = os.path.join(self.tmp.name, "deep", "nested", "f.txt")
        result = self._call(target, "x")
        self.assertNotIn("error", result)
        self.assertTrue(os.path.exists(target))

    def test_write_to_directory_path_returns_error(self):
        result = self._call(self.tmp.name)
        self.assertIn("error", result)

    def test_tools_registry_contains_write_file(self):
        names = [t["name"] for t in file_tools.TOOLS]
        self.assertIn("write_file", names)


if __name__ == "__main__":
    unittest.main()
