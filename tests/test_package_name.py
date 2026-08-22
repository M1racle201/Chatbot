"""JobMatchAgent 包名回归测试。"""

import importlib
import unittest


class TestPackageName(unittest.TestCase):
    def test_imports_from_jobmatchagent_package(self):
        package = importlib.import_module("jobmatchagent")
        self.assertEqual(package.__name__, "jobmatchagent")


if __name__ == "__main__":
    unittest.main()
