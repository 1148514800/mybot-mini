import json
import tempfile
import unittest
from pathlib import Path

from mybot.storage.session import Session, SessionManager


class SessionTests(unittest.TestCase):
    def test_prompt_history_contains_only_recent_messages(self) -> None:
        session = Session(
            key="cli:direct",
            messages=[
                {"role": "assistant", "content": "old"},
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "latest"},
            ],
        )

        self.assertEqual(
            session.build_prompt_history(max_recent_messages=3),
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "latest"},
            ],
        )

    def test_load_ignores_legacy_summary_and_save_drops_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            manager = SessionManager(workspace)
            path = workspace / "sessions" / "cli_direct.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "meta", "summary": "legacy summary"}),
                        json.dumps({"role": "user", "content": "hello"}),
                    ]
                ),
                encoding="utf-8",
            )

            session = manager.get_or_create("cli:direct")
            self.assertEqual(
                session.messages, [{"role": "user", "content": "hello"}]
            )
            manager.save(session)

            saved_lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(saved_lines), 1)
            self.assertEqual(
                json.loads(saved_lines[0]), {"role": "user", "content": "hello"}
            )


if __name__ == "__main__":
    unittest.main()
