"""Bounded, read-only Pin history at actual SQLite commit boundaries.

Event schema v1 is unchanged. DB v2 records commit ranges, including arbitrary
host batches; migration records only the old database's current boundary. Old
unrecorded boundaries are UNKNOWN, never inferred from adjacency or timestamps.
"""
import hashlib,json
from .event_schema import Event,StoreError
from ..agent.decision_provenance import quote_evidence,NOTICE


class DecisionTimeline:
    def __init__(self,store,sid):self.store,self.sid=store,sid
    def view(self,*,boundary=None,limit=100):
        if type(limit) is not int or not 1<=limit<=100:raise StoreError('decision_limit')
        with self.store.connection() as db:
            db.execute('SAVEPOINT decision_read')
            try:return self._view(db,boundary,limit)
            finally:db.execute('RELEASE decision_read')
    def _view(self,db,boundary,limit):
        session=self.store._session(db,self.sid);current=session['seq']
        if boundary is None:boundary=current
        if type(boundary) is not int or boundary<0 or boundary>current:raise StoreError('unknown_decision_boundary')
        known=db.execute('SELECT 1 FROM event_commits WHERE session_id=? AND end_sequence=?',(self.sid,boundary)).fetchone()
        if boundary!=0 and known is None:raise StoreError('unknown_decision_boundary')
        boundaries=[r[0] for r in db.execute('SELECT end_sequence FROM event_commits WHERE session_id=? AND end_sequence<=? ORDER BY end_sequence DESC LIMIT 200',(self.sid,boundary))]
        first=db.execute('SELECT start_sequence FROM event_commits WHERE session_id=? ORDER BY end_sequence LIMIT 1',(self.sid,)).fetchone()
        # At most 100 adds + 100 terminal transitions under existing Pin quota.
        events=db.execute("SELECT * FROM events WHERE session_id=? AND event_type IN ('pin.added','pin.superseded','pin.revoked') ORDER BY sequence LIMIT 201",(self.sid,)).fetchall()
        if len(events)>200:raise StoreError('decision_history_limit')
        def committed(seq):
            r=db.execute('SELECT start_sequence,end_sequence FROM event_commits WHERE session_id=? AND end_sequence>=? ORDER BY end_sequence LIMIT 1',(self.sid,seq)).fetchone()
            return r['end_sequence'] if r and r['start_sequence']<=seq else None
        items={};changes=[]
        for row in events:
            p=json.loads(row['payload']);event=Event(self.sid,row['event_id'],row['event_type'],row['timestamp'],p,row['source'],row['privacy_class'],row['schema_version'])
            if hashlib.sha256(event.canonical().encode()).hexdigest()!=row['canonical']:raise StoreError('stored_event_invalid')
            seq=row['sequence'];end=committed(seq)
            if row['event_type']=='pin.added':
                try:
                    item=quote_evidence(db,self.sid,p['source_message_id'],[p['start'],p['end']],p['content'])
                    item['source_verified']=True
                except StoreError as exc:
                    # Keep lifecycle metadata, never promote a damaged/redacted quote.
                    item=dict(session_id=self.sid,source_message_id=p['source_message_id'],source_span=[p['start'],p['end']],
                        source_role='user',original_quote=None,source_verified=False,source_error=str(exc))
                item.update(pin_id=p['pin_id'],category=p['category'],provenance_kind='host_confirmed_pin' if item['source_verified'] else 'unverified_pin_record',
                    semantic_classification='host_selected_category_only',confirmation_event_id=row['event_id'],
                    confirmation_event_sequence=seq,valid_from=end,valid_until=None,current_lifecycle_status='active',
                    added_sequence=seq,ended_sequence=None,superseded_by=None)
                items[p['pin_id']]=item
            else:
                item=items.get(p['pin_id'])
                if item is None or item['current_lifecycle_status']!='active':raise StoreError('decision_transition_invalid')
                item.update(valid_until=end,ended_sequence=seq,current_lifecycle_status='revoked' if row['event_type']=='pin.revoked' else 'superseded',superseded_by=p.get('new_pin_id'))
                changes.append(dict(event_id=row['event_id'],sequence=seq,committed_boundary=end,pin_id=p['pin_id'],status=item['current_lifecycle_status'],new_pin_id=p.get('new_pin_id')))
        selected=[]
        for item in items.values():
            # Internal events in an atomic replace have the same committed end.
            if item['added_sequence']>boundary:continue
            item['ever_effective']=None if item['valid_from'] is None or item['ended_sequence'] is not None and item['valid_until'] is None else item['valid_until'] is None or item['valid_from']<item['valid_until']
            item['trusted_at_boundary']=item['source_verified']
            item['status_at_boundary']='active' if item['ended_sequence'] is None or item['ended_sequence']>boundary else item['current_lifecycle_status']
            selected.append(item)
        selected.sort(key=lambda p:p['added_sequence'],reverse=True)
        return dict(session_id=self.sid,boundary=boundary,current_boundary=current,items=selected[:limit],omitted=max(0,len(selected)-limit),
            changes=[c for c in changes if c['sequence']<=boundary][-limit:],notice=NOTICE,
            historical_boundaries_complete=first is None or first[0]==1,
            known_boundaries=[0,*sorted(boundaries)],execution_authority_restored=False)
