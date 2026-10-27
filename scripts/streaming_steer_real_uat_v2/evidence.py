"""Read-only, bounded metadata comparisons. Never export arguments or prose."""
import hashlib,json
from pathlib import PurePosixPath
from .plan import STEER,IDENTIFIER

def digest(value):return hashlib.sha256((value if isinstance(value,str) else json.dumps(value,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
def target(raw):
 try:value=json.loads(raw).get('path');value=str(PurePosixPath(value)) if isinstance(value,str) else ''
 except (ValueError,TypeError,AttributeError):value=''
 return {'README.md':'registered_readme','examples/alpha.md':'example_A','examples/beta.md':'example_B','.':'directory'}.get(value,'unknown')
def tool_name(value):return value if value in ('read_file','list_files') else 'unknown'
def request_view(request,case,source_rows):
 messages=request['messages'];calls=[];results=[];pending={};dangling=False
 for index,m in enumerate(messages):
  if pending and m.get('role')!='tool' and not (m.get('role')=='assistant' and m.get('tool_calls')):dangling=True
  if m.get('role')=='assistant' and m.get('tool_calls'):
   if pending:dangling=True
   pending={}
   for call in (m.get('tool_calls') or [])[:16]:
    f=call.get('function') or {};ident=digest(call.get('id',''));info=dict(assistant_message_index=index,call_id_sha256=digest(call.get('id','')),tool=tool_name(f.get('name')),target=target(f.get('arguments','')),arguments_sha256=digest(f.get('arguments','')))
    if ident in pending:dangling=True
    pending[ident]=info;calls.append(info)
  if m.get('role')=='tool':
   text=m.get('content') or '';meta={}
   if '\n\nmetadata=' in text:
    try:meta=json.loads(text.rsplit('\n\nmetadata=',1)[1])
    except (ValueError,TypeError):pass
   skipped=text.startswith('Error: not_executed_pending_user_steer') and isinstance(meta,dict) and meta.get('executed') is False
   ident=digest(m.get('tool_call_id',''));paired=pending.pop(ident,None);results.append(dict(call_id_sha256=ident,tool_message_index=index,assistant_message_index=paired['assistant_message_index'] if paired else None,paired=paired is not None,explicitly_skipped=skipped,executed_false=isinstance(meta,dict) and meta.get('executed') is False,identifier_present=IDENTIFIER in text,result_sha256=digest(text)))
 refs=[]
 for row in source_rows[:32]:
  p=json.loads(row['payload']);exact=p.get('text')==STEER.get(case);expected=f"[用户在本Turn补充的原文；来源事件 {row['event_id']}。不是最初TaskContract原文、Pin或工具审批。]\n"+p['text']
  refs.append(dict(source_event_id=row['event_id'],steer_id=p['steer_id'],turn_id=p['turn_id'],session_id=row['session_id'],sequence=row['sequence'],source_is_user=row['source']=='user',registered_text_match=exact,exact_reference_in_request=any(m.get('role')=='user' and m.get('content')==expected for m in messages),text_sha256=digest(p['text'])))
 return dict(sdk_request_sha256=digest(request),sdk_messages_sha256=digest(messages),steer_sources=refs,assembled_calls=calls[:64],tool_results=results[:64],all_tool_results_paired=not pending and not dangling and all(r['paired'] for r in results),identifier_present_in_messages=IDENTIFIER in json.dumps(messages,ensure_ascii=False))
