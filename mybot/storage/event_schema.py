"""Version-one host event contracts. No request bodies, approvals or tool arguments."""
from dataclasses import dataclass, asdict
import json
import re
import time
import uuid

VERSION = 1
ID = re.compile(r'^[a-f0-9]{32}$')
CATEGORIES = ('current_goal','user_constraint','confirmed_decision','open_question','pending_work')
STATUSES = ('completed','failed','cancelled','output_truncated','output_filtered','empty_response',
            'unknown_finish','content_filtered','provider_error','response_unconfirmed','empty_reply','interrupted','execution_uncertain','stopped')
FIELDS = {
 'steer.queued': {'turn_id':str,'steer_id':str,'client_request_id':str,'text':str},
 'steer.resolved': {'turn_id':str,'steer_id':str,'state':str,'cause':str},
 'conversation.created': {'title':str},
 'user.message': {'turn_id':str,'content':str,'truncated':bool},
 'assistant.message': {'turn_id':str,'content':str,'truncated':bool},
 'turn.started': {'turn_id':str,'owner_pid':int},
 'turn.finished': {'turn_id':str,'status':str},
 'turn.interrupted': {'turn_id':str,'status':str,'reason':str},
 'turn.reviewed': {'turn_id':str},
 'tool.started': {'turn_id':str,'tool_id':str,'name':str,'side_effect':bool},
 'tool.finished': {'turn_id':str,'tool_id':str,'success':bool,'effect':str},
 'model.started': {'turn_id':str,'purpose':str},
 'model.finished': {'turn_id':str,'status':str},
 'model.failed': {'turn_id':str,'reason':str},
 'context.compacted': {'turn_id':str,'status':str,'omitted_turns':int},
 'context.cleared': {},
 'pin.added': {'pin_id':str,'category':str,'content':str,'source_message_id':str,'start':int,'end':int},
 'pin.revoked': {'pin_id':str,'expected_revision':int},
 'pin.superseded': {'pin_id':str,'new_pin_id':str,'expected_revision':int},
}


class StoreError(RuntimeError): pass


def identifier(): return uuid.uuid4().hex


@dataclass(frozen=True)
class Event:
    session_id: str
    event_id: str
    event_type: str
    timestamp: float
    payload: dict
    source: str = 'host'
    privacy_class: str = 'metadata'
    schema_version: int = VERSION

    @classmethod
    def create(cls, session_id, event_type, payload, *, source='host', privacy_class='metadata'):
        return cls(session_id,identifier(),event_type,time.time(),dict(payload),source,privacy_class,2 if event_type.startswith('steer.') else VERSION)

    def canonical(self):
        validate(self)
        return json.dumps(asdict(self),sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(',',':'))


def validate(event):
    if type(event.schema_version) is not int or event.schema_version != (2 if event.event_type.startswith('steer.') else VERSION): raise StoreError('event_version')
    if not ID.fullmatch(event.session_id) or not ID.fullmatch(event.event_id): raise StoreError('event_id')
    if type(event.timestamp) not in (float,int) or not 0 < event.timestamp < 1e12: raise StoreError('event_time')
    fields = FIELDS.get(event.event_type)
    if fields is None or type(event.payload) is not dict or set(fields) != set(event.payload): raise StoreError('event_payload_fields')
    if any(type(event.payload[k]) is not kind for k,kind in fields.items()): raise StoreError('event_payload_types')
    if event.source not in ('host','user','model','user_confirmed','recovery'): raise StoreError('event_source')
    if event.privacy_class not in ('chat','metadata'): raise StoreError('event_privacy')
    p=event.payload
    for key in ('turn_id','tool_id','pin_id','new_pin_id','source_message_id','steer_id'):
        if key in p and not ID.fullmatch(p[key]): raise StoreError('payload_id')
    if any(type(value) is str and len(value)>32768 for value in p.values()): raise StoreError('event_text_limit')
    if 'status' in p and p['status'] not in (*STATUSES,'complete','tool_calls','not_needed','deterministic','semantic_applied','semantic_reused','semantic_applied_partial','semantic_applied_pruned','fallback','omitted'):
        raise StoreError('event_status')
    if 'reason' in p and p['reason'] not in ('process_stopped','cancelled','request_failed','storage_failed','runtime_failed','incomplete_turn'): raise StoreError('event_reason')
    if event.event_type == 'tool.started' and not re.fullmatch(r'[a-zA-Z0-9_]{1,80}',p['name']): raise StoreError('tool_name')
    if 'effect' in p and p['effect'] not in ('none','possible','changed'): raise StoreError('tool_effect')
    if 'purpose' in p and p['purpose'] not in ('agent','compaction'): raise StoreError('model_purpose')
    if event.event_type.startswith('pin.') and event.source!='user_confirmed': raise StoreError('pin_requires_user')
    if event.event_type=='user.message' and event.source!='user': raise StoreError('user_message_source')
    if event.event_type=='assistant.message' and event.source not in ('model','host'): raise StoreError('assistant_source')
    if event.event_type=='turn.reviewed' and event.source!='user_confirmed': raise StoreError('review_requires_user')
    if event.event_type=='steer.queued' and (event.source!='user' or not 1<=len(p['text'])<=2000 or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',p['client_request_id'])):raise StoreError('steer_source')
    if event.event_type=='steer.resolved' and (event.source!='host' or p['state'] not in ('applied','not_applied','discarded_on_stop') or p['cause'] not in ('next_step','no_next_step','budget','stop')):raise StoreError('steer_resolution')
    if event.event_type not in ('steer.queued','steer.resolved','pin.added','pin.revoked','pin.superseded','user.message','assistant.message','turn.reviewed') and event.source not in ('host','recovery'):raise StoreError('host_event_source')
    if event.event_type=='pin.added' and (p['category'] not in CATEGORIES or not 0 <= p['start'] < p['end'] or not 1<=len(p['content'])<=512): raise StoreError('pin_contract')
