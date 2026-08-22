"""write_file 工具单元测试：除 VECTOR_DB 外任意路径可写。"""

import os
import tempfile
import unittest
import glob
import time
from unittest.mock import patch

from jobmatchagent import config
from jobmatchagent.tools import file_tools


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


class TestLoadFileTextExtensions(unittest.TestCase):
    """load_file 支持 Markdown / HTML / JSON / 代码等研发文档。"""

    def test_load_markdown_and_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "README.md")
            py = os.path.join(tmp, "example.py")
            with open(md, "w", encoding="utf-8") as file:
                file.write("# 标题\n正文内容")
            with open(py, "w", encoding="utf-8") as file:
                file.write("def add(a, b):\n    return a + b")

            md_result = file_tools.load_file(md)
            py_result = file_tools.load_file(py)

            self.assertNotIn("error", md_result)
            self.assertNotIn("error", py_result)
            self.assertIn("标题", md_result["content"])
            self.assertIn("def add", py_result["content"])


class TestSaveLongOutput(unittest.TestCase):
    """save_long_output：长文本落盘，只返回路径和大小。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = os.path.join(self.tmp.name, "output")
        os.makedirs(self.output)

    def _call(self, filename, content="长" * 5000, kind="text"):
        with patch.object(file_tools, "OUTPUT_DIR", self.output):
            return file_tools.save_long_output(filename, content, kind)

    def test_saves_content_and_returns_path_without_body(self):
        result = self._call("论文.md", "论文正文" * 1000, kind="paper")
        self.assertNotIn("error", result)
        self.assertNotIn("content", result)
        self.assertIn("note", result)
        self.assertTrue(os.path.exists(result["path"]))
        with open(result["path"], encoding="utf-8") as file:
            self.assertEqual(file.read(), "论文正文" * 1000)

    def test_kind_adds_default_extension(self):
        result = self._call("paper", "内容", kind="paper")
        self.assertEqual(result["filename"], "paper.md")

    def test_html_output_uses_html_extension(self):
        result = self._call("page", "<h1>标题</h1>", kind="html")
        self.assertEqual(result["filename"], "page.html")

    def test_rejects_path_traversal(self):
        result = self._call("../escape.txt")
        self.assertIn("error", result)

    def test_tools_registry_contains_save_long_output(self):
        names = [t["name"] for t in file_tools.TOOLS]
        self.assertIn("save_long_output", names)


class TestRunPythonScript(unittest.TestCase):
    """run_python_script 工具：临时脚本执行后自动删除。"""

    def test_run_prints_output(self):
        result = file_tools.run_python_script("print(6 * 7)")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("42", result["stdout"])

    def test_run_reports_script_error(self):
        result = file_tools.run_python_script("raise ValueError('boom')")
        self.assertNotEqual(result["exit_code"], 0)
        self.assertIn("boom", result["stderr"])

    def test_run_timeout_returns_error(self):
        result = file_tools.run_python_script(
            "import time; time.sleep(5)", timeout=1
        )
        self.assertIn("error", result)
        self.assertIn("超时", result["error"])

    def test_run_kills_nested_subprocess_on_timeout(self):
        """超时应终止整棵进程树：孙进程不能被放过，也不能阻塞等待其退出。"""
        done_file = os.path.join(tempfile.gettempdir(), "jobmatchagent_nested_done.txt")
        if os.path.exists(done_file):
            os.remove(done_file)
        self.addCleanup(lambda: os.path.exists(done_file) and os.remove(done_file))
        # 孙进程 B：睡 8 秒后写完成标记；若被进程树清理，标记永不出现
        b_code = (
            "import time\n"
            "time.sleep(8)\n"
            "open(" + repr(done_file) + ", 'w').write('done')"
        )
        # 父脚本 A：启动 B 后自己长时间等待
        a_code = (
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', " + repr(b_code) + "])\n"
            "time.sleep(30)"
        )
        start = time.time()
        result = file_tools.run_python_script(a_code, timeout=3)
        elapsed = time.time() - start
        self.assertIn("超时", result["error"])
        self.assertLess(elapsed, 6.0, f"超时后不应阻塞等待孙进程退出，实际耗时 {elapsed:.1f}s")
        time.sleep(2.5)  # 给孙进程充足时间——若未被杀死会写下完成标记
        self.assertFalse(
            os.path.exists(done_file), "孙进程应随进程树一起被终止"
        )

    def test_run_cleans_up_temp_file(self):

        pattern = os.path.join(tempfile.gettempdir(), "jobmatchagent_run_*.py")
        before = set(glob.glob(pattern))
        file_tools.run_python_script("pass")
        after = set(glob.glob(pattern))
        self.assertEqual(before, after)

    def test_tools_registry_contains_run_python_script(self):
        names = [t["name"] for t in file_tools.TOOLS]
        self.assertIn("run_python_script", names)


if __name__ == "__main__":
    unittest.main()
