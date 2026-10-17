"""Independent synthetic initial routing benchmark. Gold enters ONLY selection_metrics."""
import hashlib
import json
from ..config import PROJECT_DIR, GatewayConfig
from ..mcp_client.router import AdaptiveToolRouter
from .tool_retrieval import synthetic_catalog


def selection_metrics(selected, required, acceptable):
    selected, required, acceptable = set(selected),set(required),set(acceptable)
    hits = len(selected & required)
    return {'positive':bool(required),'multi':len(required)>1,
            'hit':bool(hits) if required else None,
            'precision':len(selected & acceptable)/len(selected) if selected else None,
            'recall':hits/len(required) if required else None,
            'full_coverage':required<=selected if required else None,
            'false_abstention':not selected if required else None,
            'correct_abstention':not selected if not required else None,
            'false_preselection':bool(selected) if not required else None,
            'selected_count':len(selected),'irrelevant_preselected_count':len(selected-acceptable),
            'missing_required_count':len(required-selected),
            'redundant_selected_count':len(selected-required),
            'multi_tool_full_coverage':required<=selected if len(required)>1 else None}


def summarize(rows):
    positives=[r for r in rows if r['positive']]
    negatives=[r for r in rows if not r['positive']]
    multi=[r for r in rows if r['multi']]
    precision=[r for r in positives if r['precision'] is not None]
    def mean(group,key):return sum(r[key] for r in group)/len(group) if group else None
    return {'cases':len(rows),'positive_denominator':len(positives),'negative_denominator':len(negatives),
            'multi_denominator':len(multi),'precision_denominator':len(precision),
            'hit_rate':mean(positives,'hit'),'precision':mean(precision,'precision'),
            'recall':mean(positives,'recall'),'full_coverage_rate':mean(positives,'full_coverage'),
            'false_abstention_rate':mean(positives,'false_abstention'),
            'correct_abstention_rate':mean(negatives,'correct_abstention'),
            'false_preselection_rate':mean(negatives,'false_preselection'),
            'mean_irrelevant_selected_tools':mean(negatives,'irrelevant_preselected_count'),
            'multi_tool_full_recall':mean(multi,'full_coverage'),
            'mean_missing_required_tools':mean(multi,'missing_required_count'),
            'mean_redundant_selected_tools':mean(multi,'redundant_selected_count'),
            'mean_selected_tools':mean(rows,'selected_count'),
            'schema_chars':sum(r.get('selected_schema_chars',0) for r in rows),
            'routing_overhead_ms':sum(r.get('routing_overhead_ms',0) or 0 for r in rows)}


def route_query(query,catalog,context_manager):
    # Runtime boundary: query + Catalog and the existing ContextManager ONLY.
    return AdaptiveToolRouter(catalog).route(query,messages=[{'role':'system','content':'Synthetic routing benchmark'},
        {'role':'user','content':query}],turns=[],plan=type('PlanView',(),{'steps':[]})(),context_manager=context_manager)


def load_cases():
    doc=json.loads((PROJECT_DIR/'evals/tool_routing_cases.json').read_text())
    cases=doc['cases']; names=synthetic_catalog().entries.keys()
    if doc['version']!=1 or len({c['case_id'] for c in cases})!=len(cases):raise ValueError('Invalid routing cases')
    for c in cases:
        if (set(c)!=set(('case_id','query','required_tools','acceptable_tools','language','category','split'))
            or c['split'] not in ('design','heldout') or not set(c['required_tools'])<=set(c['acceptable_tools'])<=names):
            raise ValueError('Invalid routing case')
    return cases


def evaluate(split=None):
    if split not in (None,'design','heldout'):raise ValueError('Invalid routing split')
    from ..agent.context_manager import ContextManager
    rows=[]
    for policy in ('legacy','selective'):
        catalog=synthetic_catalog('hybrid')
        catalog.config.update(routing_mode='adaptive',selection_policy=policy,eager_tool_threshold=4,preselect_limit=3)
        context=ContextManager(GatewayConfig(context_enabled=True,context_max_chars=160000))
        for case in load_cases():
            if split and case['split']!=split:continue
            decision=route_query(case['query'],catalog,context)
            rows.append({'case_id':case['case_id'],'policy':policy,'language':case['language'],'category':case['category'],
                'split':case['split'],**decision.diagnostics(), 'selected_schema_chars':decision.selected_schema_chars,
                **selection_metrics(decision.selected_tool_names,case['required_tools'],case['acceptable_tools'])})
    def grouped(key):
        return {value:{p:summarize([r for r in rows if r[key]==value and r['policy']==p]) for p in ('legacy','selective')}
                for value in sorted({r[key] for r in rows})}
    return {'mode':'offline','actual_tokens':None,'actual_cost':None,'live_task_success_rate':None,
            'algorithm_version':'lexical-evidence-v1.1','case_sha256':hashlib.sha256((PROJECT_DIR/'evals/tool_routing_cases.json').read_bytes()).hexdigest(),
            'overall':{p:summarize([r for r in rows if r['policy']==p]) for p in ('legacy','selective')},
            'by_split':grouped('split'),'by_language':grouped('language'),'by_category':grouped('category'),'results':rows}
