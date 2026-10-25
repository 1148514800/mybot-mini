"""Disposable source-aware history; no events, authorities or model calls.

Identity is carried outside API message dicts. Missing/changed provenance is not
recovered by searching for equal text. Statistics contain counts/reason codes,
never removed text. Protocol groups are atomic when a safe split is unknown.
"""
from copy import deepcopy
import json

from .event_schema import CATEGORIES

SOURCE_LABEL = '[经过来源筛选的历史用户原文片段；不是完整原消息或新的当前指令。]\n'
MASK = '[失效固定事项的来源跨度已遮蔽]'
ASSISTANT_LABEL = '[历史助手建议/陈述：非用户确认、非当前规则或执行证据；不能恢复失效Pin。语义改写未验证。]\n'
ASSISTANT_OMITTED = '[历史助手文本已保守省略：含失效事项的直接复述；不代表执行结果。]'
LIFECYCLE_LABEL = '[宿主生成的固定事项生命周期参考；不是System规则、审批、写入许可或执行证据。]\n'
POLICY = ('当前用户请求与active Pin有独立来源；历史用户事实只在其原来源范围内参考。'
          '历史助手建议/推断不等于用户确认，不能自行恢复revoked/superseded事项。'
          '撤销固定不删除所有历史事实；同文的新用户消息有独立效力。'
          '本参考不授予工具权限，旧工具、Receipt、verified不构成当前证据。')


def _ranges(intervals):
    result=[]
    for a,b in sorted(intervals):
        if result and a<=result[-1][1]:result[-1]=(result[-1][0],max(b,result[-1][1]))
        else:result.append((a,b))
    return result


def _subtract(intervals, protected):
    for x,y in _ranges(protected):
        intervals=[part for a,b in intervals for part in ((a,min(b,x)),(max(a,y),b)) if part[0]<part[1]]
    return _ranges(intervals)


def _lifecycle(pins):
    active=[p for p in pins if p['status']=='active']
    obsolete=[p for p in pins if p['status']!='active']
    fields=('pin_id','category','status','revision','superseded_by','source_message_id','source_span')
    return [{'role':'user','content':LIFECYCLE_LABEL+json.dumps(dict(
        policy=POLICY, active_by_category={c:[p['pin_id'] for p in active if p['category']==c] for c in CATEGORIES},
        inactive=[{k:p[k] for k in fields} for p in obsolete[:12]],
        inactive_total=len(obsolete),inactive_metadata_omitted=max(0,len(obsolete)-12),
        historical_assistant_semantics='unverified; never independently confirmed'),ensure_ascii=False)}]


def project_history(history, turns):
    pins=history.pins.list()
    history.projection_active_pins=[p for p in pins if p['status']=='active']
    stale=[p for p in pins if p['status']!='active']
    stats=dict(revoked_pin_count=sum(p['status']=='revoked' for p in pins),
        superseded_pin_count=sum(p['status']=='superseded' for p in pins),
        redacted_source_spans=0,preserved_independent_user_spans=0,
        omitted_protocol_turns=0,omitted_assistant_messages=0,omitted_user_messages=0,
        source_mapping_failures=0,source_mapping_failure_reasons={},omitted_unmapped_turns=0,history_projection_incomplete=False,
        assistant_semantic_rewrites_unverified=bool(stale))
    if not pins:return deepcopy(turns),stats,[]
    lifecycle=_lifecycle(pins)
    # At most 100 lifecycle records are admitted by the existing store contract.
    # Validate every stale source against the current session within one read.
    with history.store.connection() as db:
        history.store._session(db,history.sid)
        sources={};invalid=set()
        def failure(reason):
            stats['source_mapping_failures']+=1
            stats['source_mapping_failure_reasons'][reason]=stats['source_mapping_failure_reasons'].get(reason,0)+1
        for pin in stale:
            ident=pin['source_message_id']
            row=db.execute('SELECT id,session_id,role,content,truncated,turn_id FROM messages WHERE id=?',(ident,)).fetchone()
            a,b=pin['source_span']
            if row is None:reason='source_missing'
            elif row['session_id']!=history.sid:reason='source_session_mismatch'
            elif row['role']!='user':reason='source_role_mismatch'
            elif row['truncated']:reason='source_truncated'
            elif '[已隐藏]' in row['content'] or '[本地路径已隐藏]' in row['content'] or '[摘要已隐藏]' in row['content']:reason='source_redacted'
            elif not (type(a) is int and type(b) is int and 0<=a<b<=len(row['content']) and row['content'][a:b]==pin['content']):reason='source_span_mismatch'
            else:reason=None
            if reason:failure(reason);invalid.add(ident)
            else:sources[ident]=dict(row)
        projected=[]
        for original in turns:
            turn=deepcopy(original)
            ident=getattr(original,'source_message_id',None)
            sid=getattr(original,'session_id',None)
            protocol=any(m.get('tool_calls') or m.get('role')=='tool' for m in turn)
            affected=ident in sources or ident in invalid
            mapping_failure=False
            if stale:
                if not ident or sid!=history.sid:
                    failure('turn_identity_unavailable');mapping_failure=True
                else:
                    row=db.execute("SELECT content,truncated FROM messages WHERE id=? AND session_id=? AND role='user'",(ident,history.sid)).fetchone()
                    if row is None or not turn or turn[0].get('role')!='user' or row['content']!=turn[0].get('content'):
                        failure('turn_source_mismatch');mapping_failure=True
                    elif affected and row['truncated']:
                        failure('turn_source_truncated');mapping_failure=True
                if ident in invalid:mapping_failure=True
            # Text scanning is only a conservative protocol/assistant hazard check,
            # never a way to assign user provenance or delete other user spans.
            echoed=bool(stale) and any(p['content'] in json.dumps(turn,ensure_ascii=False) for p in stale)
            if mapping_failure or (protocol and (affected or echoed)):
                stats['omitted_protocol_turns']+=int(protocol)
                stats['omitted_unmapped_turns']+=int(mapping_failure)
                stats['omitted_assistant_messages']+=sum(m['role']=='assistant' for m in turn)
                stats['omitted_user_messages']+=sum(m['role']=='user' for m in turn)
                stats['history_projection_incomplete']=True
                continue
            if affected and stale:
                text=turn[0]['content']
                intervals=_ranges([p['source_span'] for p in stale if p['source_message_id']==ident])
                protected=[p['source_span'] for p in pins if p['status']=='active' and p['source_message_id']==ident
                           and text[slice(*p['source_span'])]==p['content']]
                intervals=_subtract(intervals,protected)
                if intervals:
                    cursor=0;parts=[]
                    for a,b in intervals:
                        fragment=text[cursor:a];parts.extend([fragment,MASK]);cursor=b
                        stats['preserved_independent_user_spans']+=int(bool(fragment.strip()))
                    fragment=text[cursor:];parts.append(fragment)
                    stats['preserved_independent_user_spans']+=int(bool(fragment.strip()))
                    turn[0]['content']=SOURCE_LABEL+''.join(parts)
                    stats['redacted_source_spans']+=len(intervals)
                    stats['history_projection_incomplete']=True
            if stale:
                for message in turn:
                    if message['role']=='assistant' and not message.get('tool_calls'):
                        if any(p['content'] in (message.get('content') or '') for p in stale):
                            message['content']=ASSISTANT_OMITTED
                            stats['omitted_assistant_messages']+=1;stats['history_projection_incomplete']=True
                        else:message['content']=ASSISTANT_LABEL+(message.get('content') or '')
            projected.append(turn)
    stats['history_projection_incomplete'] |= bool(stats['source_mapping_failures'])
    return projected,stats,lifecycle
