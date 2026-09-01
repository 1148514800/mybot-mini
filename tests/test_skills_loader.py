import asyncio
import tempfile
import unittest
from pathlib import Path

from mybot.skills.loader import SkillsLoader
from mybot.tools.file_tools import ReadFileTool


class SkillsLoaderTests(unittest.TestCase):
    def test_multiline_description_is_flattened_for_skill_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            skill_dir = workspace / "skills" / "xiaohongshu-skills"
            skill_dir.mkdir(parents=True)
            skill_dir.joinpath("SKILL.md").write_text(
                "---\n"
                "name: xiaohongshu-skills\n"
                "description: |\n"
                "  小红书自动化技能集合。\n"
                "  支持发布、搜索和互动。\n"
                "version: 1.0.0\n"
                "---\n",
                encoding="utf-8",
            )

            skill = SkillsLoader(workspace).list_skills()[0]

        self.assertEqual(
            skill["description"],
            "小红书自动化技能集合。 支持发布、搜索和互动。",
        )

    def test_workspace_skill_location_is_readable_by_file_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            skill_dir = workspace / "skills" / "browser"
            skill_dir.mkdir(parents=True)
            skill_dir.joinpath("SKILL.md").write_text(
                "---\nname: browser\ndescription: Browser automation.\n---\n",
                encoding="utf-8",
            )

            skill = SkillsLoader(workspace).list_skills()[0]
            result = asyncio.run(ReadFileTool(workspace).execute(skill["path"]))

        self.assertEqual(
            skill["path"], str(Path("skills") / "browser" / "SKILL.md")
        )
        self.assertTrue(result.startswith("---\nname: browser"))


if __name__ == "__main__":
    unittest.main()
