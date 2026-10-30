"""Phase 07 tests: local fixtures and simulated models, never real API calls."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

import mybot.config as config_module
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.context_manager import ContextBudgetError, ContextManager
from mybot.config import GatewayConfig
from mybot.skills.registry import SkillRegistry
from mybot.tools import build_default_tool_registry
from scripts.check_session import response, call, assert_pairs


class SkillsChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve().resolve()
        self.skills = self.root / "skills"
        self.skills.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.body = "# BODY_ONLY_ON_LOAD\nUse read_file; never execute scripts."
        for name in ("file-summary", "code-review"):
            self.write_skill(name)
        self.requests, self.effects = [], []
        self.config = GatewayConfig(skills_enabled=True, skills_path=self.skills,
                                    context_enabled=False,
                                    workspace=self.workspace, debug=False)
        self.redirect = contextlib.redirect_stdout(io.StringIO())
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        self.agent = self.build_agent()

    def write_skill(self, name, header=None, body=None):
        directory = self.skills / name
        directory.mkdir(exist_ok=True)
        text = f"---\n{header or ('name: '+name+chr(10)+'description: >'+chr(10)+'  Use for local files:'+chr(10)+'  summarize or review.')}\n---\n{self.body if body is None else body}\n"
        directory.joinpath("SKILL.md").write_text(text)
        directory.joinpath("references").mkdir(exist_ok=True)
        directory.joinpath("references/check.txt").write_text("REFERENCE_ONLY_ON_DEMAND")
        return directory

    def build_agent(self):
        async def create(**kwargs):
            self.requests.append(kwargs)
            if self.config.context_enabled:
                self.assertLessEqual(ContextManager.count(kwargs["messages"],kwargs["tools"]),self.config.context_token_budget['input_limit'])
            return self.effects.pop(0)
        return AgentLoop(N(chat=N(completions=N(create=create))),self.config,
                         build_default_tool_registry(self.workspace),ContextBuilder(self.workspace))

    async def test_disabled_old_behavior(self):
        self.config.skills_enabled = False
        self.config.skills_path = self.root / "missing"
        agent = self.build_agent()
        self.effects = [response("hello")]
        await agent.handle_message("hello")
        self.assertEqual(len(self.requests),1)
        self.assertIsNone(agent.skills)
        self.assertNotIn("load_skill",str(self.requests[0]["tools"]))
        self.assertNotIn("file-summary",self.requests[0]["messages"][0]["content"])

    async def test_metadata_discovery_order_and_no_body_read(self):
        registry = SkillRegistry(self.skills)
        self.assertEqual([m["name"] for m in registry.index()],["code-review","file-summary"])
        self.assertIn("files:",registry.index()[0]["description"])
        path = self.skills / "file-summary/SKILL.md"
        with path.open("ab") as stream: stream.write(b'\xff')
        # Undecodable Markdown body cannot prevent metadata-only discovery.
        self.assertEqual(len(SkillRegistry(self.skills).index()),2)
        with self.assertRaisesRegex(ValueError,"UTF-8"): registry.read("file-summary")

    async def test_startup_index_only_and_irrelevant_task(self):
        self.effects = [response("hello")]
        await self.agent.handle_message("hello")
        system = self.requests[0]["messages"][0]["content"]
        self.assertIn("file-summary",system)
        self.assertNotIn("BODY_ONLY_ON_LOAD",system)
        self.assertNotIn("REFERENCE_ONLY_ON_DEMAND",system)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.agent.plan.mode,"DIRECT")

    async def test_model_load_reference_and_real_file_tools(self):
        self.workspace.joinpath("a.txt").write_text("actual contents")
        self.effects = [response(calls=[call("s","load_skill",'{"name":"file-summary"}')]),response(calls=[call("ref","read_skill_reference",'{"name":"file-summary","path":"references/check.txt"}'),call("r","read_file",'{"path":"a.txt"}')]),response("reviewed")]
        self.assertEqual(await self.agent.handle_message("summarize a.txt"),"reviewed")
        self.assertIn("BODY_ONLY_ON_LOAD",str(self.requests[1]["messages"]))
        self.assertNotIn("BODY_ONLY_ON_LOAD",self.requests[1]["messages"][0]["content"])
        self.assertIn("REFERENCE_ONLY_ON_DEMAND",str(self.requests[2]["messages"]))
        assert_pairs(self,self.agent.session.history())
        self.assertEqual(len([m for m in self.agent.session.history() if m["role"]=="tool"]),3)

    async def test_invalid_metadata_yaml_and_fields(self):
        invalid = ['name: Bad\ndescription: ok','name: a--b\ndescription: ok','name: file-summary\ndescription: ""', 'name: file-summary\ndescription: 3','name: file-summary\ndescription: ok\ndescription: duplicate','name: file-summary\ndescription: [broken', 'name: file-summary\ndescription: !!python/object/apply:os.system ["touch unsafe"]','name: file-summary\ndescription: ok\nmetadata: {version: 1}','name: file-summary\ndescription: ok\ncompatibility: '+ 'x'*501, 'name: file-summary\ndescription: '+ 'x'*1025]
        for header in invalid:
            self.write_skill("file-summary",header)
            with self.subTest(header=header),self.assertRaises(ValueError): SkillRegistry(self.skills)

    async def test_duplicate_and_directory_mismatch(self):
        self.write_skill("zz-alias","name: file-summary\ndescription: alias")
        with self.assertRaisesRegex(ValueError,"Duplicate"): SkillRegistry(self.skills)
        self.skills.joinpath("zz-alias/SKILL.md").write_text("---\nname: other\ndescription: ok\n---\nbody")
        with self.assertRaisesRegex(ValueError,"directory"): SkillRegistry(self.skills)

    async def test_symlinks_and_path_traversal_rejected(self):
        registry = self.agent.skills
        for path in ("/etc/passwd","../outside","references/../../outside","references/../SKILL.md","references//check.txt","references\\check.txt"):
            with self.subTest(path=path),self.assertRaises(ValueError): registry.read("file-summary",path)
        ref = self.skills / "file-summary/references/link.txt"
        ref.symlink_to(self.workspace / "anything")
        with self.assertRaisesRegex(ValueError,"symlink"): registry.read("file-summary","references/link.txt")
        link = self.skills / "file-summary/references/sub"
        link.symlink_to(self.workspace,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,"symlink"): registry.read("file-summary","references/sub/anything.txt")
        self.skills.joinpath("alias").symlink_to(self.skills / "file-summary",target_is_directory=True)
        with self.assertRaisesRegex(ValueError,"symlink"): SkillRegistry(self.skills)

    async def test_reference_allowlist_and_missing_or_changed_files(self):
        registry = self.agent.skills
        for path in ("scripts/run.py","assets/a.txt","references/run.sh","references/run.py"):
            with self.assertRaises(ValueError): registry.read("file-summary",path)
        self.assertFalse((await self.agent._execute("read_skill_reference",'{"name":"file-summary","path":"SKILL.md"}')).success)
        with self.assertRaises(ValueError): registry.read("unknown")
        with self.assertRaises(ValueError): registry.read("file-summary","references/missing.txt")
        self.write_skill("file-summary","name: file-summary\ndescription: changed")
        with self.assertRaisesRegex(ValueError,"changed"): registry.read("file-summary")

    async def test_scripts_never_executed(self):
        self.write_skill("file-summary",body="```python\nopen('unsafe','w').write('bad')\n```\n```sh\ntouch unsafe\n```")
        with patch("os.system",side_effect=AssertionError("must not execute")),patch("subprocess.run",side_effect=AssertionError("must not execute")):
            result = await self.agent._execute("load_skill",'{"name":"file-summary"}')
        self.assertTrue(result.success)
        self.assertIn("touch unsafe",result.output)
        self.assertFalse(self.root.joinpath("unsafe").exists())
        self.assertFalse(self.workspace.joinpath("unsafe").exists())
        self.assertFalse(self.agent.tools.has_tool("shell"))

    async def test_loading_not_plan_completion_evidence(self):
        self.agent.plan.create(["review","write"])
        self.agent.plan.update(1,"in_progress")
        for name,args in (("load_skill",'{"name":"code-review"}'),("read_skill_reference",'{"name":"code-review","path":"references/check.txt"}')):
            self.assertTrue((await self.agent._execute(name,args)).success)
        self.assertFalse(self.agent.plan.active.verified)
        with self.assertRaises(ValueError): self.agent.plan.update(1,"completed")
        self.workspace.joinpath("a.txt").write_text("code")
        self.assertTrue((await self.agent._execute("read_file",'{"path":"a.txt"}')).success)
        self.agent.plan.update(1,"completed")
        self.assertEqual(self.agent.plan.steps[0].status,"completed")

    async def test_full_skill_and_reference_not_silently_clipped(self):
        self.write_skill("file-summary",body="IMPORTANT_FULL_INSTRUCTIONS" + "x"*9000)
        self.skills.joinpath("file-summary/references/check.txt").write_text("FULL_REFERENCE"+"y"*5000)
        self.config.context_enabled = True
        self.config.context_token_budget['input_limit'] = 30000
        self.config.context_tool_result_max_chars = 128
        self.effects = [response(calls=[call("s","load_skill",'{"name":"file-summary"}'),call("ref","read_skill_reference",'{"name":"file-summary","path":"references/check.txt"}')]),response("done")]
        await self.agent.handle_message("use skill")
        results = [m["content"] for m in self.requests[1]["messages"] if m["role"]=="tool"]
        self.assertEqual(results,[self.agent.skills.read("file-summary"),self.agent.skills.read("file-summary","references/check.txt")])
        self.assertTrue(all(ContextManager.marker not in text for text in results))
        assert_pairs(self,self.requests[1]["messages"])

    async def test_skill_budget_failure_before_second_request(self):
        self.write_skill("file-summary",body="x"*20000)
        self.config.context_enabled = True
        self.config.context_token_budget['input_limit'] = 6000
        self.effects = [response(calls=[call("s","load_skill",'{"name":"file-summary"}')])]
        with self.assertRaises(ContextBudgetError): await self.agent.handle_message("load skill")
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.agent.session.history(),[])
        self.assertGreater(ContextManager.count(self.requests[0]["messages"],self.requests[0]["tools"]),0)

    async def test_index_and_schemas_budgeted(self):
        self.config.context_enabled = True
        base = self.agent.context.build_messages("hello")
        self.config.context_token_budget['input_limit'] = ContextManager.count(base,None)
        with self.assertRaises(ContextBudgetError): await self.agent.handle_message("hello")
        self.assertEqual(self.requests,[])
        self.assertIn("file-summary",base[0]["content"])

    async def test_persistent_restore_no_execution_and_clear(self):
        self.config.session_backend = 'event_sqlite'
        self.config.session_event_path = self.root / 'private/events.sqlite3'
        self.agent = self.build_agent()
        self.effects = [response(calls=[call("s","load_skill",'{"name":"file-summary"}')]),response("loaded")]
        await self.agent.handle_message("skill task")
        history = self.agent.session.history()
        restored = self.build_agent()
        self.assertEqual(len(self.requests),2)
        self.assertEqual([m['role'] for m in restored.session.history()], ['user', 'assistant'])
        self.assertNotIn('BODY_ONLY_ON_LOAD', str(restored.session.history()))
        self.assertIn('不恢复授权', restored.session.history()[-1]['content'])
        self.assertEqual(restored.plan.steps,[])
        await restored.handle_message("/clear")
        self.effects = [response("hello")]
        await restored.handle_message("hello")
        self.assertEqual([m["role"] for m in self.requests[-1]["messages"]],["system","user"])
        self.assertNotIn("BODY_ONLY_ON_LOAD",str(self.requests[-1]["messages"]))

    async def test_limits_and_binary_text(self):
        path = self.skills / "file-summary/SKILL.md"
        path.write_bytes(b'---\nname: file-summary\ndescription: okay\n---\n'+b'x'*65536)
        with self.assertRaisesRegex(ValueError,"bytes"): SkillRegistry(self.skills)
        self.write_skill("file-summary")
        with patch.object(SkillRegistry,"max_skills",1),self.assertRaisesRegex(ValueError,"Too many"): SkillRegistry(self.skills)
        self.skills.joinpath("file-summary/references/check.txt").write_bytes(b'\x00binary')
        with self.assertRaisesRegex(ValueError,"text"): self.agent.skills.read("file-summary","references/check.txt")

    async def test_config_types_path_and_root_link(self):
        for section in ([],{"enabled":1},{"enabled":"true"},{"path":False},{"path":""},{"path":[]}):
            from scripts.check_lean_core_v2 import document
            doc = document(); doc['skills'] = section
            with self.assertRaises(config_module.ConfigError): config_module.config_from_document(doc)
        with patch.object(config_module,"PROJECT_DIR",self.root):
            self.assertEqual(GatewayConfig().skills_path,self.skills)
        alias = self.root / "alias"
        alias.symlink_to(self.skills,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,"symlink"): SkillRegistry(alias)
        with self.assertRaisesRegex(ValueError,"symlink"): GatewayConfig(skills_enabled=True,skills_path=alias)


def check_skills():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SkillsChecks))
    if not result.wasSuccessful(): raise AssertionError("Phase 07 Skills checks failed")


if __name__ == "__main__":
    check_skills()
