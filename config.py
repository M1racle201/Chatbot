"""应用配置：使用 os + dotenv 从 .env 读取环境变量。"""

import os

from dotenv import load_dotenv

# 项目根目录（config.py 所在目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 加载项目根目录下的 .env 文件（绝对路径，任意工作目录下运行都能找到）
load_dotenv(os.path.join(BASE_DIR, ".env"))

# DeepSeek API 密钥
DEEPSEEK_API = os.getenv("DEEPSEEK_API", "").strip()

# API 基础地址
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com").strip()

# 默认模型
MODEL_DEFAULT = os.getenv("MODEL_DEFAULT", os.getenv("MODLE_DEFAULT", "deepseek-chat")).strip()

# 系统提示词文件路径（基于项目根目录解析）
PROMPT_FILE = os.path.normpath(
    os.path.join(BASE_DIR, os.getenv("PROMPT", "prompt/system"))
)
