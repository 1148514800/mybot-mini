from __future__ import annotations

import re
from pathlib import Path


class SkillsLoader:
    def __init__(self, workspace: Path, builtin_dir: Path | None = None):
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_dir

    def list_skills(self) -> list[dict]:
        skills: list[dict] = []
        if self.workspace_skills.exists():
            skills.extend(self._scan_dir(self.workspace_skills))
        if self.builtin_skills and self.builtin_skills.exists():
            existing = {skill["name"] for skill in skills}
            skills.extend(
                skill
                for skill in self._scan_dir(self.builtin_skills)
                if skill["name"] not in existing
            )
        return skills

    def build_skills_summary(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = ["<skills>"]
        for skill in skills:
            lines.extend(
                [
                    "  <skill>",
                    f'    <name>{skill["name"]}</name>',
                    f'    <description>{skill["description"]}</description>',
                    f'    <location>{skill["path"]}</location>',
                    "  </skill>",
                ]
            )
        lines.append("</skills>")
        return "\n".join(lines)

    def _scan_dir(self, root: Path) -> list[dict]:
        skills: list[dict] = []
        for item in sorted(root.iterdir(), key=lambda path: path.name):
            skill_file = item / "SKILL.md"
            if item.is_dir() and skill_file.exists():
                skills.append(
                    {
                        "name": item.name,
                        "path": self._display_path(skill_file),
                        "description": self._get_description(skill_file),
                    }
                )
        return skills

    def _display_path(self, skill_file: Path) -> str:
        try:
            return str(skill_file.relative_to(self.workspace_skills.parent))
        except ValueError:
            return str(skill_file.resolve())

    def _get_description(self, path: Path) -> str:
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                lines = match.group(1).split("\n")
                for index, line in enumerate(lines):
                    if line.startswith("description:"):
                        value = line.split(":", 1)[1].strip()
                        if value not in {"|", ">"}:
                            return value.strip("\"'")

                        description_lines: list[str] = []
                        for continuation in lines[index + 1 :]:
                            if continuation and not continuation[0].isspace():
                                break
                            stripped = continuation.strip()
                            if stripped:
                                description_lines.append(stripped)
                        return " ".join(description_lines)
        return path.parent.name
