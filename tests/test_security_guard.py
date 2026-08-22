"""Python 脚本执行前安全检查测试。"""

import unittest

from jobmatchagent.security_guard import check_python_script
from jobmatchagent.tools import file_tools


class TestCheckPythonScript(unittest.TestCase):
    def test_allows_simple_calculation(self):
        result = check_python_script("print(6 * 7)")
        self.assertEqual(result["verdict"], "allow")

    def test_blocks_os_system(self):
        result = check_python_script("import os\nos.system('whoami')")
        self.assertEqual(result["verdict"], "block")
        self.assertTrue(
            any(finding["rule"] == "dangerous_call" for finding in result["findings"])
        )

    def test_blocks_shell_subprocess(self):
        result = check_python_script(
            "import subprocess\nsubprocess.run('dir', shell=True)"
        )
        self.assertEqual(result["verdict"], "block")

    def test_warns_list_subprocess_but_allows(self):
        result = check_python_script(
            "import subprocess, sys\n"
            "subprocess.Popen([sys.executable, '-c', 'pass'])"
        )
        self.assertEqual(result["verdict"], "allow")
        self.assertTrue(
            any(finding["level"] == "warn" for finding in result["findings"])
        )

    def test_blocks_dynamic_code(self):
        result = check_python_script("eval('1 + 1')\nexec('x = 1')")
        self.assertEqual(result["verdict"], "block")

    def test_blocks_network_import(self):
        result = check_python_script(
            "import requests\nrequests.get('https://example.com')"
        )
        self.assertEqual(result["verdict"], "block")

    def test_blocks_delete_operation(self):
        result = check_python_script("import os\nos.remove('/tmp/a.txt')")
        self.assertEqual(result["verdict"], "block")

    def test_blocks_sensitive_file_write(self):
        result = check_python_script("open('.env', 'w').write('x')")
        self.assertEqual(result["verdict"], "block")

    def test_syntax_error_is_blocked(self):
        result = check_python_script("def broken(:")
        self.assertEqual(result["verdict"], "block")


class TestRunPythonScriptGate(unittest.TestCase):
    def test_run_python_script_refuses_unsafe_script(self):
        result = file_tools.run_python_script(
            "import os\nos.system('echo unsafe')"
        )
        self.assertIn("error", result)
        self.assertIn("安全检查", result["error"])

    def test_run_python_script_still_runs_safe_script(self):
        result = file_tools.run_python_script("print(6 * 7)")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("42", result["stdout"])


if __name__ == "__main__":
    unittest.main()
