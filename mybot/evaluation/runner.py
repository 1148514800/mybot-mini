from __future__ import annotations

import asyncio
import contextlib
import io
import hashlib
import json
import math
import subprocess
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace as N

from ..agent.planning import Plan
from ..agent.context import ContextBuilder
from ..config import GatewayConfig, PROJECT_DIR, build_client
from ..tools import build_default_tool_registry
from .grader import grade, summarize
from .artifacts import retain_outputs
from .trace import Trace, TracedAgent, TracedClient


def safe_path(path):
    if not isinstance(path,str) or not path:
        raise ValueError("Invalid fixture/artifact path")
    p = PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or '\\' in path or p.as_posix() != path:
        raise ValueError('Invalid fixture/artifact path')
    return path


def load_cases(path=PROJECT_DIR / 'evals/cases.json'):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(document,dict) or document.get('version') not in (1,2) or not isinstance(document.get('cases'), list) or not 1 <= len(document['cases']) <= 100:
        raise ValueError('Invalid evaluation case format/version')
    seen = set()
    for case in document['cases']:
        if not isinstance(case['id'], str) or not case['id'].replace('-', '').isalnum() or case['id'] in seen:
            raise ValueError('Invalid or duplicate case ID')
        seen.add(case['id'])
        if not isinstance(case['prompt'], str) or not case['prompt'] or not isinstance(case['expect'], dict):
            raise ValueError('Invalid case prompt/rubric')
        if case.get('expected_skill') not in (None, 'file-summary', 'code-review'):
            raise ValueError('Invalid expected skill')
        for path, value in case['fixtures'].items():
            safe_path(path)
            fixture_text(value)
        if 'document' in case['expect']:
            safe_path(case['expect']['document']['path'])
        for path in case['expect'].get('files', {}):
            safe_path(path)
    return document['cases']


def fixture_text(value):
    if isinstance(value, dict):
        count = value.get('count')
        if type(count) is not int or not 0 <= count <= 10000:
            raise ValueError('Invalid fixture repetition')
        value = value.get('prefix', '') + value['repeat'] * count + value.get('suffix', '')
    if not isinstance(value, str) or len(value) > 100000:
        raise ValueError('Invalid fixture text/size')
    return value


class OfflineClient:
    """A fixed benchmark script, never a simulation of real model competence."""
    def __init__(self, case, group):
        # Explicit scripts only; auto does not manufacture expected skill selection.
        group = normalize_group(group)
        self.actions = list(case['offline'].get(group+'_actions',case['offline']['actions']))
        self.reply, self.step = case['offline']['reply'], 0
        self.chat = N(completions=N(create=self.create))

    async def create(self, **kwargs):
        self.step += 1
        calls = None
        if self.actions:
            action = self.actions.pop(0)
            calls = [N(id=f'offline-{self.step}', function=N(name=action['tool'], arguments=json.dumps(action['args'])))]
        return N(choices=[N(message=N(content=None if calls else self.reply, tool_calls=calls))], usage=None)


def normalize_group(group):
    if type(group) is bool:  # compatibility for Phase 8 Python callers
        return 'auto' if group else 'off'
    if group not in ('off','auto','guided'):
        raise ValueError('Unknown evaluation group; use off,auto,guided')
    return group


def select_cases(cases, case_ids, maximum):
    if case_ids is not None:
        ids = case_ids.split(',') if isinstance(case_ids,str) else list(case_ids)
        if not ids or len(ids)!=len(set(ids)) or any(not isinstance(i,str) or not i for i in ids):
            raise ValueError('Invalid/duplicate case IDs')
        by_id = {c['id']:c for c in cases}
        if any(i not in by_id for i in ids):
            raise ValueError('Unknown case ID')
        cases = [by_id[i] for i in ids]
    return cases[:maximum]


def task_prompt(case, group):
    return case['prompt'] + ('\n请先读取 '+case['expected_skill']+' Skill，再按其说明完成上述任务。' if group=='guided' else '')


async def evaluate(cases=None, *, live=False, repeats=1, max_cases=10, max_requests=200,
                   timeout=30.0, base_config=None, client_factory=None, groups=('off','auto'), case_ids=None, retain_artifacts=None):
    if type(live) is not bool or type(repeats) is not int or not 1 <= repeats <= 20:
        raise ValueError('live must be boolean; repeats must be 1-20')
    if type(max_cases) is not int or not 1 <= max_cases <= 100 or type(max_requests) is not int or not 1 <= max_requests <= 10000:
        raise ValueError('Invalid case/model request limit')
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= 600:
        raise ValueError('timeout must be finite and in (0, 600]')
    groups = groups.split(',') if isinstance(groups,str) else list(groups)
    groups = [normalize_group(g) for g in groups]
    if not groups or len(set(groups))!=len(groups):
        raise ValueError('Invalid/duplicate comparison groups')
    retention_cases = {hashlib.sha256(json.dumps(c,sort_keys=True,ensure_ascii=False).encode()).hexdigest() for c in load_cases()} if retain_artifacts is not None else set()
    cases = select_cases(load_cases() if cases is None else cases,case_ids,max_cases)
    base = base_config or GatewayConfig(session_persist=False, skills_enabled=False, context_enabled=True,
                                       context_max_chars=40000, context_tool_result_max_chars=1000,
                                       debug=False, max_react_steps=16)
    common = replace(base, session_persist=False, debug=False, mcp_enabled=False, mcp_servers={},
                     mcp_discovery={"enabled":False})
    budget = {'used': 0, 'maximum': max_requests}
    results = []
    client = None
    if live:
        # Disable SDK retry requests, so every actual API attempt is bounded and traced.
        client = client_factory(common) if client_factory else build_client(common).with_options(max_retries=0)
    try:
        for repeat in range(1, repeats + 1):
            for case in cases:
                for group in groups:
                    if group=='guided' and not case.get('expected_skill'):
                        continue
                    enabled = group!='off'
                    prompt = task_prompt(case,group)
                    trace = Trace()
                    trace.paths = set(case['fixtures']) | set(case['expect'].get('files', {})) | {'.'}
                    if 'document' in case['expect']:
                        trace.paths.add(case['expect']['document']['path'])
                    started = time.perf_counter()
                    with tempfile.TemporaryDirectory(prefix='mybot-eval-') as folder:
                        workspace = Path(folder).resolve() / 'workspace'
                        workspace.mkdir()
                        for path, value in case['fixtures'].items():
                            target = workspace / safe_path(path)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text(fixture_text(value), encoding='utf-8')
                        config = replace(common, workspace=workspace, skills_enabled=enabled,
                                         session_path=Path(folder) / 'state/session.json')
                        agent, reply = None, ''
                        if budget['used'] >= max_requests:
                            trace.error = 'model_request_limit'
                        else:
                            try:
                                raw_client = client if live else (client_factory(config, case) if client_factory else OfflineClient(case, group))
                                agent = TracedAgent(TracedClient(raw_client, trace, budget), config,
                                                    build_default_tool_registry(workspace), ContextBuilder(workspace), trace=trace)
                                # Plan output may contain task-derived text: never write it to terminal/report.
                                with contextlib.redirect_stdout(io.StringIO()):
                                    reply = await asyncio.wait_for(agent.handle_message(prompt), timeout)
                            except asyncio.TimeoutError:
                                trace.error = 'case_timeout'
                            except Exception:
                                trace.error = trace.error or ('case_setup_error' if agent is None else 'agent_error')
                        plan = agent.plan if agent is not None else Plan()
                        if trace.finish_reason == 'react_limit':
                            trace.error = trace.error or 'react_limit'
                        try:
                            score = grade(case, reply, workspace, trace, plan, group)
                        except Exception:
                            trace.error = trace.error or 'grading_error'
                            score = {'task_success':False,'process_clean':False,'instruction_followed':False,'strict_pass':False, 'checks':{}, 'grading_reasons':['grading_error'],
                                     'review_findings':None, 'manual_review_required':True}
                        score.setdefault('diagnostics',{})['runtime'] = {
                            'category':'model_request_timeout' if trace.error=='llm_timeout_or_cancelled' else trace.error,
                            'case_timeout_seconds':timeout,'request_timeout_seconds':common.request_timeout_seconds,
                            'max_react_steps':common.max_react_steps,
                            'output_limit_reached':any(e.get('finish_reason')=='length' for e in trace.events)}
                        retention = {'status':'disabled'}
                        if retain_artifacts is not None:
                            signature = hashlib.sha256(json.dumps(case,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                            if signature not in retention_cases:
                                retention = {'status':'refused','reason':'only_builtin_synthetic_cases'}
                            else:
                                try:
                                    retention = retain_outputs(case,reply,workspace,retain_artifacts,(common.api_key,))
                                except OSError:
                                    retention = {'status':'failed','reason':'artifact_io_error'}
                        metrics = trace.metrics()
                        metrics['skill_usage'].update(expected_skill=case.get('expected_skill'),
                            expected_loaded=case.get('expected_skill') in trace.skills if case.get('expected_skill') else None,
                            unexpected_skills=[n for n in dict.fromkeys(trace.skills) if n!=case.get('expected_skill')])
                        results.append({'case_id':case['id'], 'repeat':repeat, 'skills_enabled':enabled,'group':group,
                                        'prompt_variant':'guided' if group=='guided' else 'original',
                                        'response_source':'live_client' if live else 'fixed_offline_script',
                                        'offline_script_label':case['offline'].get('guided_script_label') if not live and group=='guided' else ('fixed task script, no automatic skill selection' if not live else None),
                                        'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                                        'expected_skill':case.get('expected_skill'), **metrics, **score,
                                        'planning_completed':all(s.status=='completed' for s in plan.steps) if plan.steps else None,
                                        'plan_states':[s.status for s in plan.steps], 'mode':plan.mode,
                                        'duration_seconds':time.perf_counter()-started, 'error':trace.error,
                                        'final_output':{'chars':len(reply),'sha256':hashlib.sha256(reply.encode()).hexdigest()},
                                        'retained_artifacts':retention,'trace':trace.events})
    finally:
        if live and client is not None and hasattr(client, 'close'):
            await client.close()
    commit = subprocess.run(['git','rev-parse','HEAD'],cwd=PROJECT_DIR,text=True,capture_output=True).stdout.strip() or None
    return {'version':2,'diagnostic_version':1,'scoring_semantics':'outcome/process/instruction independent; auto skill use optional','mode':'live' if live else 'offline',
            'ability_score':live, 'git_commit':commit,
            'benchmark_sha256':hashlib.sha256(json.dumps(cases,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'model':common.model if live else 'offline-script', 'provider':common.provider if live else 'offline',
            'created_at':datetime.now(timezone.utc).isoformat(),
            'config':{'context_recent_turns':common.context_recent_turns,'context_summary_max_chars':common.context_summary_max_chars,
                      'session_max_turns':common.session_max_turns,'repeats':repeats,'max_cases':max_cases,'max_requests':max_requests,'timeout_seconds':timeout,
                      'max_react_steps':common.max_react_steps,'max_completion_tokens':common.max_completion_tokens,
                      'request_timeout_seconds':common.request_timeout_seconds,'context_enabled':common.context_enabled,
                      'context_max_chars':common.context_max_chars,'context_tool_result_max_chars':common.context_tool_result_max_chars,
                      'retain_artifacts':retain_artifacts is not None,'session_persist':False,'groups':list(groups)},
            'results':results,'overall':summarize(results)}


def save_report(report, directory=PROJECT_DIR / 'runs/evals'):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids silently overwriting a previous repeat/run.
    import uuid
    path = directory / (report['mode'] + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.json')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    return path
