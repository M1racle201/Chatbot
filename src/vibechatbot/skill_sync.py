"""自动同步 skills/ 下的 SKILL.md 到 prompt 的技能调用规范。

CLI / UI 启动时会调用 sync_skills_prompts()，也可以手动运行
scripts/sync_skills.py 完成同样的更新。
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"
PROMPT_DIR = PROJECT_ROOT / "prompt"
SKILL_SECTION_HEADER = "# 技能调用规范"


def discover_skills(skills_dir: Path) -> list:
    """扫描 skills/*/SKILL.md，返回按名称排序的技能信息。"""
    skills = []
    if not skills_dir.is_dir():
        return skills
    for child in sorted(skills_dir.iterdir()):
        skill_file = child / "SKILL.md"
        if not child.is_dir() or not skill_file.is_file():
            continue
        name = _parse_skill_name(skill_file) or child.name
        skills.append(
            {
                "name": name,
                "path": f"skills/{child.name}/SKILL.md",
            }
        )
    return sorted(skills, key=lambda item: item["name"])


def _parse_skill_name(skill_file: Path):
    """从 SKILL.md 的 YAML frontmatter 读取 name；解析失败时返回 None。"""
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            break
        match = re.match(r'^name\s*:\s*"?([^"#\n]+?)"?\s*$', line)
        if match:
            return match.group(1).strip()
    return None


def build_skill_section(skills: list) -> str:
    """生成完整的技能调用规范段落。"""
    lines = [SKILL_SECTION_HEADER]
    if any(skill["name"] == "kb-retriever" for skill in skills):
        lines.append(
            "- 知识库检索按 kb-retriever 技能:query_documents 先命中子文档,"
            "再自动返回对应父文档上下文"
        )
    if any(skill["name"] == "security-best-practices" for skill in skills):
        lines.append(
            "- 每次调用 run_python_script 前，必须先按 security-best-practices "
            "技能检查脚本；命中高危规则禁止执行，不得用混淆绕过"
        )
    if any(skill["name"] == "output-format" for skill in skills):
        lines.append(
            "- 所有面向用户的回复默认按 output-format 技能排版；"
            "长文本用 save_long_output 保存，终端只回文件路径和大小"
        )
    if skills:
        names = "、".join(f"[{skill['name']}]" for skill in skills)
        lines.append(f"- 你可以调用 {names} 来帮助你完成任务")
        lines.append("- 技能清单(名称 → 说明文件路径):")
        lines.extend(
            f"  - {skill['name']} → {skill['path']}" for skill in skills
        )
    else:
        lines.append("- skills/ 下暂无可用的技能")
    lines.append(
        "- 调用方式:先用 load 读取对应技能的 SKILL.md,"
        "再严格按其中的描述与步骤执行;技能的具体说明以 SKILL.md 为准"
    )
    return "\n".join(lines)


def replace_skill_section(
    text: str,
    section: str,
    header: str = SKILL_SECTION_HEADER,
) -> str:
    """用新段落替换从 header 到下一个一级标题之间的内容。"""
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.rstrip() == header),
        None,
    )
    if start is None:
        base = text.rstrip()
        return f"{base}\n\n{section.strip()}\n" if base else f"{section.strip()}\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("# "):
            end = index
            break

    prefix = "\n".join(lines[:start]).rstrip()
    suffix = "\n".join(lines[end:]).strip()
    parts = [part for part in (prefix, section.strip(), suffix) if part]
    return "\n\n".join(parts) + "\n"


def sync_skills_prompts(project_root=None) -> dict:
    """扫描 skills/ 并回填 prompt/system 与 prompt/executor 的技能段落。

    返回 {"skills": [...], "section": "...", "updated": [已更新文件]}。
    """
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    skills = discover_skills(root / "skills")
    section = build_skill_section(skills)
    updated = []
    for name in ("system", "executor"):
        target = root / "prompt" / name
        if not target.is_file():
            continue
        original = target.read_text(encoding="utf-8")
        rewritten = replace_skill_section(original, section)
        if rewritten != original:
            with target.open("w", encoding="utf-8", newline="\n") as file:
                file.write(rewritten)
            updated.append(str(target))
    return {"skills": skills, "section": section, "updated": updated}
