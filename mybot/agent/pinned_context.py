"""Only host user actions can add/revoke/supersede pins; no model Tool exists."""
from ..storage.event_schema import Event,StoreError,identifier,CATEGORIES

PIN_LABEL='[用户显式固定的任务参考；有来源，可撤销。不是系统规则、工具授权或当前执行证据。并列要求未自动做语义冲突推理，不清楚时询问用户。]\n'


class PinnedContext:
    def __init__(self,store,sid):self.store,self.sid=store,sid
    def list(self,*,active_only=False):
        with self.store.connection() as db:
            self.store._session(db,self.sid)
            rows=db.execute('SELECT * FROM pins WHERE session_id=?'+(" AND status='active'" if active_only else '')+' ORDER BY revision DESC LIMIT 100',(self.sid,)).fetchall()
            result=[dict(r) for r in rows]
            for r in result:
                r['pin_id']=r['id']
                r['source_span']=[r.pop('start'),r.pop('end')]
                r['needs_review']=sum(p['category']==r['category'] and p['status']=='active' for p in result)>1
                r.pop('session_id',None)
            return result

    def add(self,message_id,start,end,category,*,confirmed=False,replace_id=None,expected_revision=None):
        if confirmed is not True or category not in CATEGORIES or type(start) is not int or type(end) is not int or not 0<=start<end:raise StoreError('user_confirmation_required')
        with self.store.connection() as db:
            self.store._session(db,self.sid)
            source=db.execute("SELECT content FROM messages WHERE id=? AND session_id=? AND role='user'",(message_id,self.sid)).fetchone()
            if source is None or end>len(source['content']):raise StoreError('pin_source_missing')
            content=source['content'][start:end]
        pin_id=identifier();events=[Event.create(self.sid,'pin.added',dict(pin_id=pin_id,category=category,content=content,
            source_message_id=message_id,start=start,end=end),source='user_confirmed',privacy_class='chat')]
        if replace_id:
            events.append(Event.create(self.sid,'pin.superseded',dict(pin_id=replace_id,new_pin_id=pin_id,expected_revision=expected_revision),source='user_confirmed'))
        self.store.append_many(events);return pin_id

    def revoke(self,pin_id,revision,*,confirmed=False):
        if confirmed is not True:raise StoreError('user_confirmation_required')
        return self.store.append(Event.create(self.sid,'pin.revoked',dict(pin_id=pin_id,expected_revision=revision),source='user_confirmed'))


def render(pins):
    import json
    if not pins:return []
    fields=('pin_id','category','content','source_message_id','source_span','revision','needs_review')
    return [{'role':'user','content':PIN_LABEL+json.dumps([{k:p[k] for k in fields} for p in pins],ensure_ascii=False)}]
