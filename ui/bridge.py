"""Ink 前端拉起的 Python 后端入口（薄壳，逻辑在 vibechatbot.bridge）。"""

import os
import sys

# 未 pip install 时自动把项目 src 加入 sys.path，保证从仓库直接运行可用
_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(os.path.dirname(_UI_DIR), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

try:
    from vibechatbot.bridge import main
except ImportError:
    print(
        "无法加载 vibechatbot，请确认项目 src 目录存在或先运行: pip install -e .",
        file=sys.stderr,
    )
    sys.exit(1)

if __name__ == "__main__":
    main()
