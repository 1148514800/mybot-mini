"""Read-only Phase 8 reinterpretation; missing evidence stays unknown."""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import json

from .grader import summarize
from .trace import PLAN_ERRORS


LEGACY_CASE_IDS = {'greeting','list-files','read-fact','multi-step','file-summary','code-review','irrelevant','missing-file','long-context','write-content'}


def analyze_report(path):
    original = json.loads(Path(path).read_text(encoding='utf-8'))
    if original.get('version') == 2:
        return original
    if original.get('version') != 1:
        raise ValueError('Unsupported evaluation report version')
    report = deepcopy(original)
    report.update(version=2,source_version=1,analysis_only=True,
                  scoring_semantics='recomputed from v1 saved checks; raw outputs/artifacts unavailable')
    for result in report['results']:
        checks = result.get('checks',{})
        task = {k:v for k,v in checks.items() if k not in ('tool_results','plan_complete','skill_selection','direct','planned')}
        # V1 has no explicit skill-use task; expected_skill is not an instruction.
        process = {k:checks.get(k) for k in ('tool_results','plan_complete','no_runtime_error','finished')}
        instruction = {'requested_plan':bool(checks.get('planned') and checks.get('plan_complete'))} if 'planned' in checks else {}
        known = lambda values: False if False in values else (None if any(v is None for v in values) else True)
        outcome = known(list(task.values())) if {'no_runtime_error','finished'}<=task.keys() else None
        clean = known(list(process.values()))
        followed = all(instruction.values()) if result['case_id'] in LEGACY_CASE_IDS else None
        events = [e for e in result.get('trace',[]) if e['event']=='tool']
        planning = [e for e in events if e['name'] in ('create_plan','update_plan') and not e['success']]
        categories = Counter(e.get('error') if e.get('error') in set(PLAN_ERRORS.values()) | {'other_tool_error'} else 'unknown' for e in planning)
        reads = Counter(e['fixture_path'] for e in events if e['name']=='read_file' and e.get('fixture_path'))
        before, created = 0, False
        for e in events:
            if e['name']=='create_plan' and e['success']: created=True
            if not created and e['name'] in ('read_file','write_file','list_files'): before+=1
        result.update(group='auto' if result['skills_enabled'] else 'off',task_success=outcome,process_clean=clean,
                      instruction_followed=followed,strict_pass=known([outcome,clean,followed]),
                      task_checks=task,process_checks=process,instruction_checks=instruction,
                      planning_failure_categories=dict(categories),planning_tool_failures=len(planning),
                      file_tools_before_plan=before,duplicate_reads=sum(n-1 for n in reads.values()),
                      duplicate_reads_complete=all(e.get('fixture_path') is not None for e in events if e['name']=='read_file'),
                      skill_usage={'loaded':bool(result['skill_selected']),'selected':result['skill_selected'],
                                   'load_calls':sum(e['name']=='load_skill' for e in events),
                                   'reference_calls':sum(e['name']=='read_skill_reference' for e in events),
                                   'extra_llm_requests':None,'extra_tokens':None},
                      grading_reasons=[prefix+k for prefix,c in (('task:',task),('process:',process),('instruction:',instruction)) for k,v in c.items() if v is False])
    report['overall'] = summarize(report['results'])
    report['analysis_limits'] = ['No raw outputs or artifacts to regrade','Planning tool_failed categories unknown; no inferred arguments',
                                 'Skill marginal request/token costs unavailable','Unknown file paths make duplicate read counts lower bounds','Custom v1 cases have unknown explicit instruction requirements']
    return report
