#!/usr/bin/env python
"""手动同步技能清单：扫描 skills/ 并回填 prompt 提示词。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jobmatchagent.skill_sync import sync_skills_prompts  # noqa: E402


def main() -> None:
    result = sync_skills_prompts()
    names = "、".join(f"[{item['name']}]" for item in result["skills"]) or "无"
    print(f"检测到技能: {names}")
    if result["updated"]:
        print("已更新:")
        for path in result["updated"]:
            print(f"  {path}")
    else:
        print("提示词已是最新,无需更新")


if __name__ == "__main__":
    main()
