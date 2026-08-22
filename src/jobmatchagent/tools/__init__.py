"""工具注册表：收集所有工具定义，提供按名称执行的能力。

新增工具方法：在 TOOLS 目录下建模块，定义 TOOLS 列表
（每项：name / description / parameters / function），并在这里导入注册。
"""

import json

from jobmatchagent.tools.file_tools import TOOLS as BASIC_TOOLS

# 全部工具定义（含执行函数）
_ALL_TOOLS = BASIC_TOOLS

# 传给模型的工具 schema（OpenAI 标准格式：type + function）
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["parameters"],
        },
    }
    for tool in _ALL_TOOLS
]

# name -> 执行函数 映射
_TOOL_FUNCTIONS = {tool["name"]: tool["function"] for tool in _ALL_TOOLS}


def execute_tool(name: str, arguments: dict) -> str:
    """按名称执行工具，返回 JSON 字符串结果。"""
    if name not in _TOOL_FUNCTIONS:
        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    try:
        result = _TOOL_FUNCTIONS[name](**arguments)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
