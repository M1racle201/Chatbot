"""应用配置：环境变量 + 项目根/数据目录统一解析。"""

import os

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


# 项目根目录（可用 VIBECHAT_ROOT 环境变量显式覆盖）
PROJECT_ROOT = os.getenv("VIBECHAT_ROOT", _find_project_root(_PACKAGE_DIR))

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

# ---- 提示词目录 ----
PROMPT_DIR = os.path.join(PROJECT_ROOT, "prompt")
PROMPT_FILE = os.path.normpath(
    os.path.join(PROJECT_ROOT, os.getenv("PROMPT", "prompt/system"))
)

# ---- DeepSeek API ----
DEEPSEEK_API = os.getenv("DEEPSEEK_API", "").strip()
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com").strip()
MODEL_DEFAULT = os.getenv("MODEL_DEFAULT", os.getenv("MODLE_DEFAULT", "deepseek-chat")).strip()
