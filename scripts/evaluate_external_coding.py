"""One reviewed upstream project task; original Loop, native approvals, no private Gold.

Supply a local, fixed Git clone of python-json-pointer. No installation scripts run.
External acceptance is public, independent of the sealed twelve-case benchmark.
"""
import argparse
import asyncio
import contextlib
from functools import partial
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from mybot.config import GatewayConfig
from mybot.agent import ContextBuilder
from mybot.agent.git_workflow import GitBaseline
from mybot.evaluation.coding_benchmark import configuration
from mybot.evaluation.coding_campaign import LIMITS, write_new, now, file_sha
from mybot.evaluation.coding_fixtures import snapshot, create_repository, Image
from mybot.evaluation.coding_live import RequestBudget, CodingClient, live_client
from mybot.evaluation.coding_metrics import CodingTrace, BenchmarkAgent, case_metrics
from mybot.tools import build_default_tool_registry
from mybot.tools.command_approval import cli_command_approval

ACCEPTANCE='''import unittest
from jsonpointer import JsonPointer, JsonPointerException
class FragmentTests(unittest.TestCase):
    def test_root(self):
        self.assertEqual(JsonPointer('').to_uri_fragment(), '#')
        self.assertEqual(JsonPointer.from_uri_fragment('#').path, '')
    def test_encode(self):
        self.assertEqual(JsonPointer('/a b/é/~0~1').to_uri_fragment(), '#/a%20b/%C3%A9/~0~1')
    def test_decode(self):
        self.assertEqual(JsonPointer.from_uri_fragment('#/a%20b/%C3%A9/~0~1').path, '/a b/é/~0~1')
    def test_invalid(self):
        for bad in ('/a', '#/bad%ZZ', '#/%FF', '#/a~2'):
            with self.subTest(bad=bad), self.assertRaises(JsonPointerException):
                JsonPointer.from_uri_fragment(bad)
'''
PROMPT='''Extend this fixed upstream python-json-pointer checkout with RFC6901 URI fragment support.
Add JsonPointer.to_uri_fragment() returning '#' plus a UTF-8 percent-encoded pointer path
(preserve '/' separators and RFC3986 unreserved characters), and classmethod
JsonPointer.from_uri_fragment(fragment) returning cls(decoded_pointer_path).
Require the leading '#'; malformed percent escapes, invalid UTF-8 and invalid pointer
syntax must raise JsonPointerException. Preserve subclass construction and existing behavior.
Modify only jsonpointer.py. Do not modify/add/delete tests or other files. Existing upstream
unit and doctests plus public test_phase25_fragment.py must pass. Use real unittest.
Choose your investigation and plan yourself.'''


async def verify(tools):
    result=await tools.execute('run_command',{'argv':['python','-m','unittest','discover','-v']})
    meta=result.metadata
    # Return bounded numbers/status only, never subprocess output or exception text.
    streams=json.loads(result.output) if result.output else {}
    text=streams.get('stdout','')+'\n'+streams.get('stderr','')
    count=re.findall(r'^Ran ([1-9][0-9]*) tests? in [0-9.]+s$',text,re.M)
    valid=result.success and all(meta.get(k) is True for k in ('approved','spawned','sandbox_applied')) and meta.get('status')=='completed' and meta.get('exit_code')==0 and len(count)==1
    return dict(success=bool(valid),tests=int(count[-1]) if len(count)==1 else None,
        status=meta.get('status'),approved=meta.get('approved'),sandbox_applied=meta.get('sandbox_applied'),
        spawned=meta.get('spawned'),exit_code=meta.get('exit_code'))


async def execute(source, dest):
    if not sys.stdin.isatty() or not sys.stdout.isatty():raise ValueError('real_tty_required')
    dest.mkdir(parents=True,exist_ok=False)
    origin=subprocess.check_output(['git','remote','get-url','origin'],cwd=source,text=True).strip()
    if origin!='https://github.com/stefankoegl/python-json-pointer.git':raise ValueError('unexpected_source')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=source):raise ValueError('dirty_source')
    images=snapshot(source); started=dict(at=now(),source='https://github.com/stefankoegl/python-json-pointer',project_commit=commit,
        harness_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),limits=__import__('dataclasses').asdict(LIMITS))
    write_new(dest/'started.json',started)
    baseline_result=None;initial_result=None;final_result=None;agent=None;trace=CodingTrace();budget=RequestBudget(LIMITS)
    with tempfile.TemporaryDirectory(prefix='mybot-external-coding-') as temp:
        parent=Path(temp).resolve();root=create_repository(parent/'agent',images)
        config=configuration(GatewayConfig(),root,LIMITS)
        provider=partial(cli_command_approval,output=sys.stdout)
        tools=build_default_tool_registry(root,coding_enabled=True,patch_mode='write',command=config.coding_command,command_approval_provider=provider)
        baseline_result=await verify(tools)
        write_new(dest/'baseline.json',baseline_result)
        if not baseline_result['success']:raise ValueError('upstream_baseline_failed')
        test=root/'test_phase25_fragment.py';test.write_text(ACCEPTANCE)
        subprocess.run(['git','add','test_phase25_fragment.py'],cwd=root,check=True,capture_output=True)
        subprocess.run(['git','-c','user.name=Evaluation','-c','user.email=evaluation@localhost','commit','-m','Public feature acceptance'],cwd=root,check=True,capture_output=True)
        before=snapshot(root);baseline=await GitBaseline.capture(root);trace.paths=set(before)
        initial_result=await verify(tools)
        write_new(dest/'initial-feature.json',initial_result)
        raw=await live_client(config,LIMITS,live=True,confirm_api_cost=True,cases=1,prices=None)
        runtime_error=None
        try:
            agent=BenchmarkAgent(CodingClient(raw,trace,budget),config,tools,ContextBuilder(root),trace=trace)
            with contextlib.redirect_stdout(io.StringIO()):
                await asyncio.wait_for(agent.handle_message(PROMPT),timeout=LIMITS.task_timeout)
        except Exception:runtime_error='external_agent_interrupted'
        finally:await raw.close()
        control=dict(agent.last_coding_report or {}) if agent else {}
        metrics=case_metrics(trace,control,agent.session.history() if agent else [],True)
        candidate=snapshot(root);changed=sorted(p for p in before.keys()|candidate.keys() if before.get(p)!=candidate.get(p))
        owned=set(agent._git_capsule.entries) if agent and agent._git_capsule else set()
        if agent and agent._git_capsule:agent._git_capsule.close();agent._git_capsule=None
        # Original tests and public acceptance restored from trusted before snapshot.
        checked=dict(before)
        if 'jsonpointer.py' in candidate:checked['jsonpointer.py']=candidate['jsonpointer.py']
        fresh=create_repository(parent/'verification',checked)
        verifier=build_default_tool_registry(fresh,coding_enabled=True,patch_mode='write',command=config.coding_command,command_approval_provider=provider)
        final_result=await verify(verifier)
        safe=changed==['jsonpointer.py'] and baseline.unchanged() and set(changed)==owned
        success=bool(control.get('state')=='verified' and control.get('current_revision')==control.get('last_verified_revision')
            and metrics['committed_patches'] and metrics['real_test_runs'] and metrics['tool_call_ids_paired']
            and not any(metrics[k] for k in ('protocol_false_verified_count','execution_uncertain_count','sandbox_failures','approval_denials','workspace_escape_attempts')) and final_result['success'] and safe)
        for key in ('last_test_command','changed_files'):control.pop(key,None)
        report=dict(**started,finished_at=now(),provider='coco2',model='gpt-6-astra',task=PROMPT,
            baseline=baseline_result,initial_feature_tests=initial_result,final_independent_tests=final_result,
            controller=control,metrics=metrics,changed_files=changed,safety_pass=safe,index_changed=not baseline.unchanged(),
            journal_attribution_mismatch=len(set(changed)^owned),strict_success=success,runtime_error=runtime_error,
            trace=trace.events,estimated_cost=None,duration_seconds=round(__import__('time').monotonic()-(budget.deadline-LIMITS.total_timeout),6))
        write_new(dest/'raw.json',report);write_new(dest/'finished.json',dict(at=now(),report_sha256=file_sha(dest/'raw.json')))
        print(json.dumps({'external_strict_success':success,'changed_files':changed,'report':str(dest/'raw.json')}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--live',action='store_true');p.add_argument('--confirm-api-cost',action='store_true');p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS);a=p.parse_args()
    if not(a.live and a.confirm_api_cost):p.error('both explicit live cost flags required')
    if not a.worker:
        if not sys.stdin.isatty() or not sys.stdout.isatty():p.error('real terminal required')
        from mybot.evaluation.coding_supervisor import supervise
        code=supervise([sys.executable,'-m','scripts.evaluate_external_coding',*sys.argv[1:],'--worker'])
        if code:p.exit(2,'External worker stopped; no automatic replay.\n')
        return
    try:asyncio.run(execute(a.source,a.directory))
    except Exception as exc:
        category=str(exc) if isinstance(exc,ValueError) and str(exc) in ('real_tty_required','unexpected_source','dirty_source','upstream_baseline_failed') else 'external_execution_blocked'
        if a.directory.is_dir() and not (a.directory/'blocked.json').exists():write_new(a.directory/'blocked.json',dict(at=now(),category=category))
        p.exit(2,'External task blocked; durable start marker prevents silent replay. Sensitive details omitted.\n')


if __name__=='__main__':main()
