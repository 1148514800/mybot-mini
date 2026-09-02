from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class MainEntrypointTests(unittest.TestCase):
    def test_direct_script_path_does_not_shadow_mcp_sdk(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        package_dir = repo_root / "mybot"
        script = textwrap.dedent(
            f"""
            from pathlib import Path
            import runpy
            import sys

            package_dir = Path({str(package_dir)!r})
            sys.path.insert(0, str(package_dir))
            runpy.run_path(
                str(package_dir / "main.py"),
                run_name="mybot_main_import_smoke",
            )
            import mcp
            print(Path(mcp.__file__).resolve())
            """
        )

        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        imported_mcp = Path(completed.stdout.strip()).resolve()
        self.assertNotEqual(imported_mcp, package_dir / "mcp" / "__init__.py")
        self.assertNotEqual(package_dir, imported_mcp.parent.parent)


if __name__ == "__main__":
    unittest.main()
