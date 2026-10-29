"""R2 equivalence checks against the exact R1 implementation; no model transport."""
import importlib
from pathlib import Path
import random
import subprocess
import sys
import unittest
from copy import deepcopy
from dataclasses import replace

from mybot.agent.context_manager import ContextManager
from mybot.agent.planning import Plan, Step
from mybot.agent.token_counter import TokenCounter
from mybot.config import GatewayConfig
from mybot.tools.base import ToolResult

BASELINE = 'd262049b1403c8873cd5b5036fd1628d044bd7d4'


def baseline(module):
    current = importlib.import_module(module)
    path = module.replace('.', '/') + '.py'
    source = subprocess.check_output(['git', 'show', BASELINE + ':' + path],
        cwd=Path(__file__).resolve().parents[1], stderr=subprocess.DEVNULL, text=True)
    namespace = dict(vars(current))
    exec(compile(source, '<R1:' + path + '>', 'exec'), namespace)
    return namespace


class LeanChecks(unittest.TestCase):
    def test_context_outputs_errors_and_input_isolation_match_r1(self):
        old = baseline('mybot.agent.context_manager')['ContextManager']
        rng = random.Random(20261028)
        config = GatewayConfig(skills_enabled=False, session_persist=False, context_enabled=True)
        cases = 0
        for mode in ('legacy_chars', 'estimate', 'strict'):
            for iteration in range(60):
                cfg = replace(config, context_enabled=mode != 'legacy_chars' or iteration % 3 != 0,
                    context_max_chars=rng.choice((256, 900, 4000)),
                    context_token_budget={'mode':mode, 'input_limit':rng.choice((512, 1700, 8000))},
                    context_tool_result_max_chars=rng.choice((128, 300, 1000)))
                turns = [[{'role':'user','content':'问题'*rng.randrange(5, 60)},
                          {'role':'assistant','content':'回答'*rng.randrange(10, 500)}]
                         for _ in range(rng.randrange(4))]
                current = [{'role':'user','content':'now'},
                    {'role':'assistant','content':None,'tool_calls':[{'id':'c','type':'function',
                        'function':{'name':'read_file','arguments':'{"path":"note"}'}}]},
                    {'role':'tool','tool_call_id':'c','content':'工具😀'*rng.randrange(10, 500)}]
                messages = [{'role':'system','content':'system'}] + [m for t in turns for m in t] + current
                if iteration % 10 == 0: messages[0]['role'] = 'user'
                if iteration % 11 == 0: current[-1]['tool_call_id'] = 'unpaired'
                tools = [{'type':'function','function':{'name':'read_file','parameters':{'type':'object'}}}]
                outcomes = []
                for cls in (old, ContextManager):
                    manager = cls(cfg)
                    if iteration % 2: manager.lifecycle_reference = [{'role':'user','content':'lifecycle'}]
                    if iteration % 3 == 0: manager._pin_messages = [{'role':'user','content':'protected pin'}]
                    plan = Plan()
                    if iteration % 2: plan.steps = [Step('inspect', 'completed', True), Step('verify')]
                    args = deepcopy((messages, tools, turns, plan))
                    original = deepcopy(args[:3])
                    try: result = ('ok', manager._prepare(*args))
                    except Exception as exc: result = ('error', type(exc).__name__, str(exc))
                    self.assertEqual(args[:3], original)
                    outcomes.append(result)
                self.assertEqual(*outcomes, (mode, iteration))
                cases += 1
        self.assertEqual(cases, 180)

    def test_measurement_dictionary_and_failures_match_r1(self):
        old = baseline('mybot.agent.token_counter')['TokenCounter']
        for text in ('', 'ASCII', '中文😀', '\\"\n', 'x'*20000):
            request = {'messages':[{'role':'user','content':text}], 'tools':None}
            self.assertEqual(list(TokenCounter.measure(request).items()), list(old.measure(request).items()))
        for request in ({'bad':float('nan')}, {'bad':object()}):
            for cls in (old, TokenCounter):
                with self.assertRaises((ValueError, TypeError)): cls.measure(request)

    def test_tool_result_text_matches_r1(self):
        old = baseline('mybot.tools.base')['ToolResult']
        for success in (True, False):
            for output in ('', 'body'):
                for error in (None, '', 'denied'):
                    for metadata in ({}, {'executed':False}):
                        args = (success, output, error, metadata)
                        self.assertEqual(ToolResult(*args).to_text(), old(*args).to_text())

    def test_runtime_imports_do_not_reach_experiments_or_scripts(self):
        code = '''
import importlib, importlib.abc, sys
class Boundary(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'scripts' or fullname.startswith(('scripts.', 'mybot.evaluation')):
            raise AssertionError('runtime crossed boundary: '+fullname)
sys.meta_path.insert(0, Boundary())
for module in ('mybot.main', 'mybot.web.__main__', 'mybot.web.server'):
    importlib.import_module(module)
from mybot.config import GatewayConfig
GatewayConfig(skills_enabled=False, mcp_enabled=False, session_persist=False)
'''
        subprocess.run([sys.executable, '-c', code], check=True,
                       cwd=Path(__file__).resolve().parents[1])


def check_lean_refactor():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LeanChecks))
    if not result.wasSuccessful(): raise SystemExit(1)


if __name__ == '__main__': check_lean_refactor()
