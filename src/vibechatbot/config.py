"""应用配置：环境变量 + 项目根/数据目录统一解析。"""

import os
import sys

from dotenv import load_dotenv

# 包目录（.../src/vibechatbot）
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_project_root(start: str) -> str:
    """从包目录向上找 pyproject.toml 所在的项目根；找不到回退 CWD。"""
    current = start
    for _ in range(5):
        if os.path.exists(os.path.join(current, "pyproject.toml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.getcwd()


def _default_project_root() -> str:
    """PyInstaller 打包后以 exe 所在目录作为项目根，便于数据/提示词外置。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return _find_project_root(_PACKAGE_DIR)


# 项目根目录（可用 VIBECHAT_ROOT 环境变量显式覆盖）
PROJECT_ROOT = os.getenv("VIBECHAT_ROOT", _default_project_root())

# 加载项目根目录下的 .env（绝对路径，任意工作目录下运行都能找到）
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ---- 运行时数据目录（统一收拢到 data/）----
DATA_DIR = os.getenv("VIBECHAT_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
CHAT_DIR = os.path.join(DATA_DIR, "CHAT")
TASK_DIR = os.path.join(DATA_DIR, "TASK")
AGENTIC_DIR = os.path.join(DATA_DIR, "AGENTIC")
OUTPUT_DIR = os.path.join(DATA_DIR, "OUTPUT")
VECTOR_DB_DIR = os.path.join(DATA_DIR, "VECTOR_DB")
HISTORY_FILE = os.path.join(CHAT_DIR, "history.json")

# ---- 文件写入白名单（write_file 工具）----
# VIBECHAT_WRITE_DIRS 用分号分隔多个目录；OUTPUT 目录始终允许
WRITE_DIRS = [
    d.strip() for d in os.getenv("VIBECHAT_WRITE_DIRS", "").split(";") if d.strip()
]

# ---- 提示词目录 ----
PROMPT_DIR = os.path.join(PROJECT_ROOT, "prompt")
PROMPT_FILE = os.path.normpath(
    os.path.join(PROJECT_ROOT, os.getenv("PROMPT", "prompt/system"))
)
MCP_CONFIG = os.getenv(
    "MCP_CONFIG",
    os.path.join(PROJECT_ROOT, "config", "mcp.json"),
)

# ---- DeepSeek API ----
DEEPSEEK_API = os.getenv("DEEPSEEK_API", "").strip()
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com").strip()
MODEL_DEFAULT = os.getenv("MODEL_DEFAULT", os.getenv("MODLE_DEFAULT", "deepseek-chat")).strip()
