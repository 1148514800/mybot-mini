"""Read-only unit preservation from actual SDK messages and real host source IDs.

No complete-turn equality metric, semantic similarity, assistant-as-user credit,
or backward inference from the final model answer. Only public fixture units.
"""
import hashlib,json
from mybot.agent.pinned_context import PIN_LABEL
from mybot.storage.context_projection import SOURCE_LABEL,MASK,LIFECYCLE_LABEL
from .plan import MESSAGES,units

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def expected_view(row,pins):
    """Independent exact-span reconstruction for these non-overlapping fixtures."""
    intervals=[]
    for p in pins:
        if p['source_message_id']!=row['id'] or p['status']=='active':continue
        a,b=p['source_span']
        if type(a) is not int or type(b) is not int or not 0<=a<b<=len(row['content']) or row['content'][a:b]!=p['content']:raise ValueError('measurement_source_span')
        intervals.append((a,b))
    if not intervals:return row['content']
    cursor=0;parts=[]
    for a,b in sorted(intervals):
        if a<cursor:raise ValueError('measurement_overlapping_fixture_spans')
        parts.extend([row['content'][cursor:a],MASK]);cursor=b
    return SOURCE_LABEL+''.join(parts)+row['content'][cursor:]

def preservation(case,history,session,request,context=None):
    context=context or {};pins=history.pins.list();rows=history.store.query("SELECT id,session_id,turn_id,role,content,truncated FROM messages WHERE session_id=? AND role='user' ORDER BY sequence",(history.sid,))
    if len(rows)>len(MESSAGES[case]):raise ValueError('measurement_unregistered_source')
    current_ids={r['id'] for r in rows if r['turn_id']==history.turn_id}
    recent={}
    for turn in session.export_turns():
        ident=getattr(turn,'source_message_id',None)
        if ident and getattr(turn,'session_id',None)==history.sid:
            recent[ident]=turn[0]['content'] if turn and turn[0].get('role')=='user' else None
    views={r['id']:expected_view(r,pins) for r in rows}
    records=[]
    for u in units(case):
        n=u['source_turn']-1
        if n>=len(rows):records.append({'unit_id':u['unit_id'],'status':'NOT_INTRODUCED'});continue
        row=rows[n];a,b=u['source_span'];content=row['content']
        valid=row['session_id']==history.sid and row['role']=='user' and not row['truncated'] and content==MESSAGES[case][n] and content[a:b]==u['content']
        identity=row['id'] in current_ids or recent.get(row['id'])==content
        expected=views[row['id']]
        candidates=[i for i,m in enumerate(request['messages']) if m.get('role')=='user' and m.get('content')==expected]
        unique_source=sum(v==expected for v in views.values())==1
        present=valid and identity and unique_source and len(candidates)==1 and u['content'] in expected
        status='PRESERVED' if present else 'UNKNOWN' if not valid or not unique_source or len(candidates)>1 else 'MISSING'
        possible=[]
        if not identity:possible.append('source_not_in_host_recent_or_current_turn')
        if context.get('history_turns_omitted'):possible.append('token_or_context_budget_history_omission')
        if context.get('omitted_protocol_turns'):possible.append('atomic_protocol_fallback')
        if context.get('source_mapping_failures'):possible.append('source_mapping_fallback')
        records.append(dict(unit_id=u['unit_id'],kind=u['kind'],source_turn=u['source_turn'],source_message_id=row['id'],source_span=u['source_span'],source_role='user',source_verified=bool(valid),host_identity_verified=identity,source_sha256=digest(content),expected_user_view_sha256=digest(expected),sdk_message_index=candidates[0] if present else None,status=status,possible_missing_causes=possible if not present else [],assistant_echo_present=any(u['content'] in (m.get('content') or '') for m in request['messages'] if m.get('role')=='assistant')))
    introduced=[r for r in records if r['status']!='NOT_INTRODUCED'];good=sum(r['status']=='PRESERVED' for r in introduced)
    return dict(historical_naming_presence=[dict(name=name,occurrences=[dict(message_index=i,role=m['role']) for i,m in enumerate(request['messages']) if name in (m.get('content') or '')]) for name in ({'S01':['photos.jsonl','assets.jsonl'],'S02':['tracks.csv','library.csv'],'S03':[]}[case])],method='exact_registered_unit_in_ID_mapped_original_user_SDK_view_v1',units=records,introduced=len(introduced),preserved=good,missing=sum(r['status']=='MISSING' for r in introduced),unknown=sum(r['status']=='UNKNOWN' for r in introduced),rate=good/len(introduced) if introduced else None,assistant_echo_counts_as_preserved=False,projection={k:context.get(k) for k in ('redacted_source_spans','preserved_independent_user_spans','omitted_protocol_turns','omitted_assistant_messages','source_mapping_failures','history_projection_incomplete','history_turns_omitted','context_truncated')})

def inclusion(request):
    pins=[];lifecycle=[]
    for m in request['messages']:
        text=m.get('content') or ''
        for label,target in ((PIN_LABEL,pins),(LIFECYCLE_LABEL,lifecycle)):
            if text.startswith(label):
                if m['role']!='user':raise ValueError('host_reference_role')
                data=json.loads(text[len(label):]);target.extend(data if isinstance(data,list) else [data])
    return dict(pins=pins,lifecycle=lifecycle,message_hashes=[dict(role=m['role'],sha256=digest(m)) for m in request['messages']],request_sha256=digest(request))
