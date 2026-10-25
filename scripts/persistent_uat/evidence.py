"""Bounded non-replayable request metadata and explicit unrelated user units."""
import hashlib,json
from mybot.agent.pinned_context import PIN_LABEL
from .plan import UNITS

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def inclusion(request):
    pins=[]
    for m in request['messages']:
        if (m.get('content') or '').startswith(PIN_LABEL):
            if m['role']!='user':raise ValueError('pin_role_not_user')
            pins.extend(json.loads(m['content'][len(PIN_LABEL):]))
    return dict(pins=pins,message_hashes=[dict(role=m['role'],sha256=digest(m)) for m in request['messages']],
        tool_names=[t['function']['name'] for t in request.get('tools',[])],request_sha256=digest(request))

def information_loss(history,turns):
    kept=history.context_turns(turns);removed=[(i,t) for i,t in enumerate(turns) if t not in kept]
    units=[]
    for i,t in removed:
        for m in t:
            if m.get('role')=='user':
                units.extend(dict(unit_id=k,turn_index=i,source_sha256=digest(m['content'])) for k,text in UNITS.items() if text in m.get('content',''))
    return dict(removed_complete_turns=len(removed),removed_message_count=sum(len(t) for _,t in removed),
        unrelated_user_unit_count=len(units),unrelated_user_units=units,
        assistant_semantic_information_loss='requires human assessment; not inferred from exact user units',raw_history_changed=False)
