"""Ink 前端拉起的 Python 后端入口（薄壳，逻辑在 vibechatbot.bridge）。"""

import sys

try:
    from vibechatbot.bridge import main
except ImportError:
    print(
        "vibechatbot 包未安装，请先在项目根目录运行: pip install -e .",
        file=sys.stderr,
    )
    sys.exit(1)

main()
