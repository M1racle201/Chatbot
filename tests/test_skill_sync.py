"""skills 自动同步脚本测试（使用临时目录，不修改真实 prompt）。"""

import tempfile
import unittest
from pathlib import Path

from jobmatchagent.skill_sync import (
    build_skill_section,
    discover_skills,
    replace_skill_section,
    sync_skills_prompts,
)


class TestSkillSync(unittest.TestCase):
    def _write_skill(self, root: Path, folder: str, name: str):
        directory = root / "skills" / folder
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: 测试技能\n---\n\n内容\n",
            encoding="utf-8",
        )

    def _make_project(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self._write_skill(root, "iterative-retrieval", "iterative-retrieval")
        self._write_skill(root, "kb-retriever", "kb-retriever")
        prompt = root / "prompt"
        prompt.mkdir()
        (prompt / "system").write_text(
            "系统提示\n\n# 技能调用规范\n- 旧内容\n\n# 对话规范\n- 对话\n",
            encoding="utf-8",
        )
        (prompt / "executor").write_text(
            "执行提示\n\n# 技能调用规范\n- 旧内容\n",
            encoding="utf-8",
        )
        return root

    def test_discover_skills_sorted_by_name(self):
        root = self._make_project()
        skills = discover_skills(root / "skills")
        self.assertEqual(
            [item["name"] for item in skills],
            ["iterative-retrieval", "kb-retriever"],
        )
        self.assertEqual(
            skills[0]["path"],
            "skills/iterative-retrieval/SKILL.md",
        )

    def test_security_skill_adds_execution_gate_line(self):
        root = self._make_project()
        self._write_skill(root, "security-best-practices", "security-best-practices")
        section = build_skill_section(discover_skills(root / "skills"))
        self.assertIn("每次调用 run_python_script 前", section)
        self.assertIn("security-best-practices", section)

    def test_output_format_skill_adds_formatting_line(self):
        root = self._make_project()
        self._write_skill(root, "output-format", "output-format")
        section = build_skill_section(discover_skills(root / "skills"))
        self.assertIn("所有面向用户的回复默认按 output-format 技能排版", section)
        self.assertIn("output-format", section)

    def test_sync_updates_both_prompts(self):
        root = self._make_project()
        result = sync_skills_prompts(root)
        self.assertEqual(len(result["updated"]), 2)

        for name in ("system", "executor"):
            text = (root / "prompt" / name).read_text(encoding="utf-8")
            self.assertIn(
                "- 你可以调用 [iterative-retrieval]、[kb-retriever] 来帮助你完成任务",
                text,
            )
            self.assertIn(
                "  - iterative-retrieval → skills/iterative-retrieval/SKILL.md",
                text,
            )
            self.assertIn(
                "  - kb-retriever → skills/kb-retriever/SKILL.md",
                text,
            )
            self.assertNotIn("knowledge/data_structure.md", text)
            self.assertNotIn("旧内容", text)

    def test_sync_is_idempotent(self):
        root = self._make_project()
        sync_skills_prompts(root)
        result = sync_skills_prompts(root)
        self.assertEqual(result["updated"], [])

    def test_empty_skills_are_reported(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "prompt").mkdir()
        (root / "prompt" / "system").write_text(
            "系统提示\n\n# 技能调用规范\n- 旧内容\n",
            encoding="utf-8",
        )
        result = sync_skills_prompts(root)
        self.assertEqual(result["skills"], [])
        text = (root / "prompt" / "system").read_text(encoding="utf-8")
        self.assertIn("skills/ 下暂无可用的技能", text)

    def test_replace_skill_section_appends_when_header_missing(self):
        section = build_skill_section([])
        text = replace_skill_section("只有开头", section)
        self.assertIn("# 技能调用规范", text)
        self.assertIn("只有开头", text)


if __name__ == "__main__":
    unittest.main()
