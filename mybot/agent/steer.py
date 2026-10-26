"""Host-owned, turn-scoped inbox. No model tool, authority or automatic replay."""
import re
from ..storage.event_schema import Event,StoreError,identifier
from ..storage.event_privacy import safe_text

class SteerInbox:
    def __init__(self,history,notify=None):self.notify=notify;self.history=history;self.turn_id=history.turn_id;self.pending=None;self.records={}
    def submit(self,expected_turn_id,client_request_id,text):
        if self.turn_id is None or self.history.status()['status']!='running':raise StoreError('rejected_inactive')
        if expected_turn_id!=self.turn_id or self.history.turn_id!=self.turn_id:raise StoreError('stale_turn')
        if not isinstance(client_request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',client_request_id):raise StoreError('rejected')
        if type(text) is not str or not text.strip() or len(text)>2000:raise StoreError('rejected')
        clean,truncated=safe_text(text,self.history.store.secrets,max_bytes=16000)
        if truncated or clean!=text:raise StoreError('steer_sensitive_or_incomplete')
        previous=self.records.get(client_request_id)
        if previous:
            if previous['text']!=text:raise StoreError('steer_id_conflict')
            return dict(previous)
        if self.pending is not None or len(self.records)>=32:raise StoreError('steer_capacity')
        eid=identifier();event=Event.create(self.history.sid,'steer.queued',dict(turn_id=self.turn_id,steer_id=eid,client_request_id=client_request_id,text=text),source='user',privacy_class='chat')
        self.history.store.append(event)
        row=dict(steer_id=eid,source_event_id=event.event_id,turn_id=self.turn_id,client_request_id=client_request_id,text=text,status='queued',cause='waiting_boundary')
        self.records[client_request_id]=row;self.pending=row
        if self.notify:self.notify(dict(type='steer_status',steer=dict(row)))
        return dict(row)
    def resolve(self,status,cause):
        if self.pending is None:return
        row=self.pending
        self.history.event('steer.resolved',dict(turn_id=self.turn_id,steer_id=row['steer_id'],state=status,cause=cause))
        row.update(status=status,cause=cause);self.pending=None
        if self.notify:self.notify(dict(type='steer_status',steer=dict(row)))
    def reference(self):
        if self.pending is None:return None
        p=self.pending
        return dict(role='user',content=f"[用户在本Turn补充的原文；来源事件 {p['source_event_id']}。不是最初TaskContract原文、Pin或工具审批。]\n"+p['text'])
    @staticmethod
    def audit(history):
        import json
        with history.store.connection() as db:
            history.store._session(db,history.sid)
            events=db.execute("SELECT event_id,event_type,payload FROM events WHERE session_id=? AND event_type IN ('steer.queued','steer.resolved') ORDER BY sequence DESC LIMIT 64",(history.sid,)).fetchall()
        rows={}
        for event in reversed(events):
            p=json.loads(event['payload']);ident=p['steer_id']
            if event['event_type']=='steer.queued':rows[ident]=dict(steer_id=ident,source_event_id=event['event_id'],**{k:p[k] for k in ('turn_id','client_request_id','text')},status='not_applied',cause='process_queue_not_restored')
            elif ident in rows:rows[ident].update(status=p['state'],cause=p['cause'])
        return list(rows.values())[-32:]
