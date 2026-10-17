"""Standalone ranking evaluation, independent of Agent task success and Phase 9 grades."""
import json
import math
from pathlib import Path
from types import SimpleNamespace as N
from ..config import PROJECT_DIR
from ..tools import ToolRegistry
from ..mcp_client.adapter import MCPToolAdapter
from ..mcp_client.discovery import MCPToolCatalog


def synthetic_catalog(mode='literal', limit=5):
    from scripts.mcp_catalog_demo_server import DEFINITIONS
    registry = ToolRegistry()
    manager = N(servers={'catalog': {'allowed_tools':list(DEFINITIONS), 'tool_policies':{n:'allow' for n in DEFINITIONS}}})
    for definition in DEFINITIONS.values():
        registry.register(MCPToolAdapter(manager,'catalog',definition))
    return MCPToolCatalog(registry, {'enabled':True,'retrieval_mode':mode,'search_limit':limit})


def load_cases():
    doc = json.loads((PROJECT_DIR/'evals/tool_retrieval_cases.json').read_text())
    assert doc['version'] == 1
    cases = doc['cases']
    assert len({c['case_id'] for c in cases}) == len(cases)
    catalog = synthetic_catalog()
    for c in cases:
        assert set(c['relevant_tools']) <= catalog.entries.keys()
        assert set(c['relevant_tools']) <= set(c['acceptable_tools']) <= catalog.entries.keys()
    return cases


def metrics(ranked, relevant, k):
    relevant = set(relevant)
    if not relevant: return None
    hits = [int(n in relevant) for n in ranked[:k]]
    dcg = sum(hit/math.log2(i+2) for i,hit in enumerate(hits))
    ideal = sum(1/math.log2(i+2) for i in range(min(k,len(relevant))))
    return {'hit':int(any(hits)), 'recall':sum(hits)/len(relevant),
            'mrr':next((1/(i+1) for i,hit in enumerate(hits) if hit),0), 'ndcg':dcg/ideal}


def summarize(rows):
    positive = [r for r in rows if r['relevant_count']]
    negative = [r for r in rows if not r['relevant_count']]
    report = {'cases':len(rows),'positive_denominator':len(positive),'negative_denominator':len(negative)}
    for k in (1,3,5):
        for key in ('hit','recall','mrr','ndcg'):
            report[f'{key}@{k}'] = sum(r['metrics'][str(k)][key] for r in positive)/len(positive) if positive else None
    report['no_match_accuracy'] = sum(not r['returned'] for r in negative)/len(negative) if negative else None
    report['false_candidate_rate'] = sum(bool(r['returned']) for r in negative)/len(negative) if negative else None
    return report


def evaluate():
    cases = load_cases()
    results = {}
    for mode in ('literal','bm25','hybrid'):
        catalog = synthetic_catalog(mode)
        rows=[]
        for case in cases:
            names=[m['name'] for m in json.loads(catalog.search(case['query']).output)['matches']]
            rows.append({'case_id':case['case_id'],'language':case['language'],'category':case['category'],
                         'split':case['split'],'relevant_count':len(case['relevant_tools']),'returned':names,
                         'metrics':{str(k):metrics(names,case['relevant_tools'],k) for k in (1,3,5)}})
        results[mode]={'overall':summarize(rows),
                       'by_language':{key:summarize([r for r in rows if r['language']==key]) for key in sorted({r['language'] for r in rows})},
                       'by_category':{key:summarize([r for r in rows if r['category']==key]) for key in sorted({r['category'] for r in rows})},
                       'by_split':{key:summarize([r for r in rows if r['split']==key]) for key in ('design','heldout')},'cases':rows}
    return {'mode':'offline','catalog_tools':35,'search_limit':5,'bm25':{'k1':1.2,'b':0.75,'field_weights':[6,3,1],
            'idf':'log(1+(N-df+0.5)/(df+0.5))','alias_weight':0.35},'agent_success_measured':False,'results':results}
