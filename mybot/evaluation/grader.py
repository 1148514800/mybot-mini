from __future__ import annotations

import json
import re
from pathlib import Path


def review_score(findings, annotations):
    """Match file AND function AND evidence, never one standalone keyword."""
    hits, false = set(), 0
    for finding in findings:
        if not isinstance(finding, dict):
            false += 1
            continue
        evidence = str(finding.get('evidence', '')).casefold()
        match = next((a for a in annotations if finding.get('file') == a['file'] and finding.get('function') == a['function']
                      and all(any(term.casefold() in evidence for term in alternatives) for alternatives in a['evidence'])), None)
        if match:
            hits.add(match['id'])
        else:
            false += 1
    tp, fn = len(hits), len(annotations) - len(hits)
    return {'true_positives':tp,'false_positives':false,'false_negatives':fn,
            'precision':tp/(tp+false) if tp+false else None,'recall':tp/(tp+fn) if tp+fn else None}


def grade(case, reply, workspace: Path, trace, plan, group):
    rules = case['expect']
    task = {'no_runtime_error':trace.error is None,'finished':trace.finish_reason == 'finished'}
    tools = [e for e in trace.events if e['event'] == 'tool']
    process = {'tool_results':all(e['success'] or e['name'] in rules.get('allowed_failures', []) for e in tools),
               'no_runtime_error':trace.error is None,'finished':trace.finish_reason == 'finished',
               'plan_complete':not plan.steps or all(s.status=='completed' for s in plan.steps)}
    instruction = {}
    for name in rules.get('tools', []):
        task['tool:'+name] = any(e['name']==name and e['success'] for e in tools)
    for path in rules.get('read_paths', []):
        task['read:'+path] = any(e['name']=='read_file' and e['success'] and e.get('fixture_path')==path for e in tools)
    for name in rules.get('failed_tools', []):
        task['failure:'+name] = any(e['name']==name and not e['success'] for e in tools)
    for word in rules.get('contains', []):
        task['fact:'+word] = word.casefold() in reply.casefold()
    for word in rules.get('forbidden', []):
        task['not:'+word] = word.casefold() not in reply.casefold()
    if rules.get('planned'):
        instruction['requested_plan'] = bool(plan.steps) and process['plan_complete']
    required_skill = case.get('required_skill') or (case.get('expected_skill') if group=='guided' else None)
    if required_skill:
        instruction['requested_skill'] = required_skill in trace.skills
        if group=='guided':
            first_load = next((i for i,e in enumerate(tools) if e['name']=='load_skill' and e['success'] and e.get('skill_name')==required_skill),len(tools))
            first_file = next((i for i,e in enumerate(tools) if e['name'] in ('read_file','write_file','list_files')),len(tools))
            instruction['requested_skill_first'] = first_load < first_file
    # The ordinary off/auto task never requires skill selection.
    for path, expected in rules.get('files', {}).items():
        target = (workspace/path).resolve()
        valid = target.is_relative_to(workspace.resolve()) and target.is_file() and target.stat().st_size <= 100000
        text = target.read_text(encoding='utf-8') if valid else ''
        task['artifact:'+path] = valid and (text==expected['exact'] if 'exact' in expected else all(s in text for s in expected['contains']))
    review = None
    if 'defects' in rules:
        found, expected = set(re.findall(r'DEFECT:\s*([A-Z_]+)',reply)), set(rules['defects'])
        tp, fp, fn = len(found&expected), len(found-expected), len(expected-found)
        review = {'true_positives':tp,'false_positives':fp,'false_negatives':fn,
                  'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None}
        task['defect_hits'], task['no_false_defects'] = not fn, not fp
    if 'review_annotations' in rules:
        try:
            document = json.loads(reply)
            findings = document['findings']
            valid = isinstance(findings,list) and all(isinstance(f,dict) and all(isinstance(f.get(k),str) and f[k].strip() for k in ('file','function','evidence','trigger','impact','fix')) for f in findings)
        except (ValueError,KeyError,TypeError):
            findings, valid = [], False
        review = review_score(findings if isinstance(findings,list) else [],rules['review_annotations'])
        task.update(review_format=valid,defect_hits=review['false_negatives']==0,no_false_defects=review['false_positives']==0)
    if 'document' in rules:
        expected = rules['document']
        target = (workspace/expected['path']).resolve()
        valid = target.is_relative_to(workspace.resolve()) and target.is_file() and target.stat().st_size<=100000
        try:
            artifact = json.loads(target.read_text(encoding='utf-8')) if valid else None
        except (ValueError,UnicodeError):
            artifact = None
        task['document_format'] = isinstance(artifact,dict)
        for key,value in expected['values'].items():
            actual = artifact.get(key) if isinstance(artifact,dict) else None
            task['decision:'+key] = (isinstance(actual,list) and all(isinstance(v,str) for v in actual) and sorted(actual)==sorted(value)) if isinstance(value,list) else actual==value
        task['no_unsupported_conclusions'] = isinstance(artifact,dict) and set(artifact)==set(expected['values'])
    if rules.get('clipped'):
        task['context_clipped'] = any(e.get('tool_result_clipped') for e in trace.events)
    outcome, clean, followed = all(task.values()), all(process.values()), all(instruction.values())
    return {'task_success':outcome,'process_clean':clean,'instruction_followed':followed,'strict_pass':outcome and clean and followed,
            'checks':task,'task_checks':task,'process_checks':process,'instruction_checks':instruction,
            'grading_reasons':[prefix+key for prefix,checks in (('task:',task),('process:',process),('instruction:',instruction)) for key,value in checks.items() if not value],
            'review_findings':review,'manual_review_required':rules.get('manual_review',False)}


def summarize(results):
    groups = {}
    for group in ('off','auto','guided'):
        items = [r for r in results if r['group']==group]
        if not items:
            continue
        stats = {'cases':len(items)}
        for metric in ('task_success','process_clean','instruction_followed','strict_pass'):
            known = [r[metric] for r in items if r.get(metric) is not None]
            stats[metric+'_count'] = sum(known)
            stats[metric+'_rate'] = sum(known)/len(known) if known else None
            stats[metric+'_unknown'] = len(items)-len(known)
        stats.update({key:sum(r.get(key,0) for r in items) for key in ('tool_calls','tool_failures','llm_requests','duration_seconds','duplicate_reads')})
        stats.update({key:sum(r[key] for r in items) if all(r.get(key) is not None for r in items) else None for key in ('input_tokens','output_tokens')})
        stats['skill_selections'] = sum(bool(r['skill_selected']) for r in items)
        reviews = [r['review_findings'] for r in items if r.get('review_findings') is not None]
        if reviews:
            tp = sum(r['true_positives'] for r in reviews)
            fp = sum(r['false_positives'] for r in reviews)
            fn = sum(r.get('false_negatives',r.get('missed',0)) for r in reviews)
            stats['review_quality'] = {'true_positives':tp,'false_positives':fp,'false_negatives':fn,
                                       'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None}
        stats['planning_tool_failures'] = sum(r.get('planning_tool_failures',0) for r in items)
        stats['manual_review_cases'] = sum(r.get('manual_review_required',False) for r in items)
        groups[group] = stats
    return groups
