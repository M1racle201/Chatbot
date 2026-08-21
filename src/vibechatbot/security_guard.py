"""run_python_script 执行前的静态安全检查。

策略是默认拒绝高危行为：脚本包含 shell 执行、动态执行、危险反序列化、
网络外联、敏感文件读写或删除操作时，直接拒绝执行。
"""

import ast
import os

from vibechatbot import config


_BLOCK_CALLS = {
    "os.system": "调用 os.system 执行 shell 命令",
    "os.popen": "调用 os.popen 执行 shell 命令",
    "os.startfile": "调用 os.startfile 启动外部程序",
    "shutil.rmtree": "递归删除目录",
    "shutil.move": "移动文件或目录",
    "os.remove": "删除文件",
    "os.unlink": "删除文件",
    "os.rmdir": "删除目录",
    "os.removedirs": "递归删除目录",
    "eval": "动态执行表达式",
    "exec": "动态执行代码",
    "compile": "动态编译代码",
    "__import__": "动态导入模块",
    "importlib.import_module": "动态导入模块",
    "pickle.load": "反序列化 pickle 数据",
    "pickle.loads": "反序列化 pickle 数据",
    "shelve.open": "打开 shelve 持久化存储",
    "yaml.load": "使用不安全方式解析 YAML",
}

_NETWORK_CALLS = {
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "requests.request",
    "requests.Session",
    "urllib.request.urlopen",
    "urllib.request.Request",
    "urllib3.request",
    "http.client.HTTPConnection",
    "http.client.HTTPSConnection",
    "httpx.get",
    "httpx.post",
    "httpx.Client",
    "aiohttp.ClientSession",
    "socket.socket",
    "ftplib.FTP",
}

_NETWORK_MODULES = {
    "requests",
    "urllib.request",
    "urllib3",
    "http.client",
    "httpx",
    "aiohttp",
    "socket",
    "ftplib",
}

_SUBPROCESS_CALLS = {
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
}

_WRITE_OR_DELETE_ATTRS = {"write_text", "write_bytes", "unlink", "rmdir"}


class _SecurityVisitor(ast.NodeVisitor):
    """收集脚本中的安全发现：block 为禁止执行，warn 为提示。"""

    def __init__(self):
        self.findings = []

    def _add(self, level: str, rule: str, message: str, node) -> None:
        self.findings.append(
            {
                "level": level,
                "rule": rule,
                "line": getattr(node, "lineno", 0),
                "message": message,
            }
        )

    def visit_Call(self, node) -> None:
        self._check_call(node)
        self.generic_visit(node)

    def visit_While(self, node) -> None:
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            self._add("warn", "resource", "检测到无界 while True 循环，可能超时", node)
        self.generic_visit(node)

    def visit_Assign(self, node) -> None:
        for target in node.targets:
            if _is_os_environ_subscript(target):
                self._add(
                    "warn", "environment", "修改 os.environ 会影响当前进程环境", target
                )
        self.generic_visit(node)

    def visit_Import(self, node) -> None:
        for alias in node.names:
            if _is_network_module(alias.name):
                self._add("block", "network", f"禁止导入网络模块 {alias.name}", node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node) -> None:
        if node.module and _is_network_module(node.module):
            self._add("block", "network", f"禁止导入网络模块 {node.module}", node)
        self.generic_visit(node)

    def _check_call(self, node) -> None:
        name = _call_name(node)
        if name in _BLOCK_CALLS:
            self._add("block", "dangerous_call", _BLOCK_CALLS[name], node)
        elif name in _NETWORK_CALLS:
            self._add("block", "network", f"禁止网络调用 {name}", node)
        elif name in _SUBPROCESS_CALLS:
            if _subprocess_uses_shell(node):
                self._add(
                    "block",
                    "subprocess",
                    "subprocess 使用 shell=True 或字符串命令",
                    node,
                )
            else:
                self._add(
                    "warn",
                    "subprocess",
                    "subprocess 调用请确认命令参数来自白名单",
                    node,
                )
        elif name == "open":
            self._check_open(node)
        elif isinstance(node.func, ast.Attribute) and node.func.attr in _WRITE_OR_DELETE_ATTRS:
            self._add(
                "block",
                "path_operation",
                f"禁止 Path.{node.func.attr} 操作",
                node,
            )

    def _check_open(self, node) -> None:
        if not node.args:
            return
        path_node = node.args[0]
        if not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str):
            return
        path = path_node.value
        mode = "r"
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        for keyword in node.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                mode = str(keyword.value.value)
        sensitive = _is_sensitive_path(path)
        if "w" in mode or "a" in mode or "x" in mode or "+" in mode:
            if sensitive:
                self._add("block", "file_write", f"禁止写入敏感路径: {path}", node)
            elif not _is_within_output(path):
                self._add(
                    "warn", "file_write", f"写入非 OUTPUT 目录: {path}", node
                )
        elif sensitive:
            self._add("block", "file_read", f"禁止读取敏感路径: {path}", node)


def _call_name(node) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        parts = []
        current = node.func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return ""


def _is_os_environ_subscript(node) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "environ"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "os"
    )


def _is_network_module(name: str) -> bool:
    return name in _NETWORK_MODULES or name.startswith("urllib.request")


def _subprocess_uses_shell(node) -> bool:
    for keyword in node.keywords:
        if (
            keyword.arg == "shell"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
        ):
            return True
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
        node.args[0].value, str
    ):
        return True
    return False


def _is_sensitive_path(path: str) -> bool:
    normalized = os.path.normpath(path).replace("\\", "/").lower()
    name = os.path.basename(normalized).lower()
    if name == ".env":
        return True
    if name.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    if name in ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"):
        return True
    if name.startswith("secret") or "credential" in name:
        return True
    if "/.ssh/" in f"/{normalized}/":
        return True
    if "vector_db" in normalized or "chroma" in normalized:
        return True
    return False


def _is_within_output(path: str) -> bool:
    try:
        target = os.path.abspath(os.path.expanduser(path))
        output = os.path.abspath(config.OUTPUT_DIR)
        return os.path.commonpath([target, output]) == output
    except (OSError, ValueError):
        return False


def check_python_script(script: str) -> dict:
    """静态检查 Python 脚本，返回 verdict=allow/block 与发现列表。"""
    if not script or not script.strip():
        return {"verdict": "allow", "reason": "空脚本", "findings": []}
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        return {
            "verdict": "block",
            "reason": "脚本无法解析",
            "findings": [
                {
                    "level": "block",
                    "rule": "syntax",
                    "line": exc.lineno or 0,
                    "message": f"脚本语法错误: {exc.msg}",
                }
            ],
        }
    visitor = _SecurityVisitor()
    visitor.visit(tree)
    findings = sorted(visitor.findings, key=lambda item: item["line"])
    blocked = [finding for finding in findings if finding["level"] == "block"]
    if blocked:
        return {
            "verdict": "block",
            "reason": "命中高危规则，拒绝执行",
            "findings": findings,
        }
    return {
        "verdict": "allow",
        "reason": "未发现高危规则",
        "findings": findings,
    }
