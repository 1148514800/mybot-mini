"""Synthetic-only trigger calibration through the real AgentLoop, not Live."""
import json,hashlib
from types import SimpleNamespace as N
from mybot.agent import AgentLoop,ContextBuilder
from mybot.agent.context_compactor import PROMPT,FIELDS,LABEL
from mybot.tools import build_default_tool_registry
from scripts.check_session import response
from .plan import MESSAGES,KEY_FACTS,config_for
from .fixtures import fingerprint

PROVIDER=dict(model='deepseek-v4.1-flash',api_key='synthetic-only-key',base_url='https://offline.invalid/v1')


def cited_response(request):
    sources=json.loads(request['messages'][-1]['content']);doc={key:[] for key in FIELDS}
    mapping={'early':'user_constraints','decisions':'decisions','unknown':'uncertainty','not_done':'pending_work'}
    for group,field in mapping.items():
        for text in KEY_FACTS[group]:
            for turn in sources:
                match=next((m for m in turn['messages'] if m['role']=='user' and text in m['content']),None)
                if match:
                    doc[field].append(dict(turn=turn['turn'],message=match['message'],quote=text));break
    # Respect the original per-field maximum; unknowns are historical user reports.
    return response(json.dumps({k:v[:6] for k,v in doc.items()},ensure_ascii=False))


async def calibrate(root):
    cfg=config_for('T03',root,PROVIDER);requests=[];states=[];before=fingerprint(root)
    async def invoke(**request):
        requests.append(request)
        if request['messages'][0]['content']==PROMPT:return cited_response(request)
        return response('仅确认设计约束和未决事项；尚未实现代码或运行测试，没有修改文件。')
    agent=AgentLoop(N(chat=N(completions=N(create=invoke))),cfg,build_default_tool_registry(root),ContextBuilder(root))
    for text in MESSAGES['T03']:
        await agent.handle_message(text);states.append(dict(agent.resources.context))
    users=[m['content'] for t in agent.session.export_turns() for m in t if m['role']=='user']
    main=[r for r in requests if r['messages'][0]['content']!=PROMPT]
    summaries=[m['content'] for r in main for m in r['messages'] if (m.get('content') or '').startswith(LABEL)]
    selected='\n'.join(summaries)
    return dict(mode='OFFLINE/SYNTHETIC',input_limit=cfg.context_token_budget['input_limit'],
        per_turn_status=[s['context_compaction_status'] for s in states],contexts=states,
        model_requests_synthetic=len(requests),summary_requests_synthetic=len(requests)-5,real_api_requests=0,
        all_early_constraints_cited=all(x in selected for x in KEY_FACTS['early']),
        latest_request_intact=main[-1]['messages'][-1]['content']==MESSAGES['T03'][-1],
        canonical_users_intact=users==MESSAGES['T03'],no_summary_persisted=LABEL not in str(agent.session.history()),
        files_unchanged=fingerprint(root)==before,message_sha256=[hashlib.sha256(x.encode()).hexdigest() for x in users],
        passed=any(s['context_compaction_status'] in ('semantic_applied','semantic_applied_pruned') for s in states)
               and users==MESSAGES['T03'] and len(requests)<=8 and all(x in selected for x in KEY_FACTS['early']))
