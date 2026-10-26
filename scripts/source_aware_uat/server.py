"""Explicit future Live adapter around unchanged production Web/Runtime/AgentLoop.

Never run without a later human GRANTED_10_REQUESTS. Offline tests inject only
MockTransport clients; no preview mode can accidentally construct a real client.
"""
import argparse,time
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
import uvicorn
from mybot.web.server import create_app
from mybot.web.security import redact
from mybot.config import build_client
from mybot.runtime_accounting import usage_values
from mybot.provider_failover import ProviderFailoverClient
from scripts.uat.server import credentials,private_json
from .plan import AUTHORIZATION,REQUIRED_AUTHORIZATION,LIMITS,MESSAGES,PIN_TEXT,BATCH,PORT,config_for,plan_hash,expected_active,pins
from .budget import Ledger,BudgetClient,BudgetStop
from .prepare import verify_frozen,fingerprint
from .evidence import inclusion,preservation


def require_authorization(value):
    if type(value) is not str or value!=REQUIRED_AUTHORIZATION:raise BudgetStop('new_live_authorization_not_granted')

def make_app(case,batch,provider_config,*,authorization=AUTHORIZATION,port=PORT):
    require_authorization(authorization)  # Before config/DB/credentials/SDK mutation.
    if case not in LIMITS or port!=PORT:raise BudgetStop('unregistered_case_or_port')
    frozen=verify_frozen(batch,provider_config)
    if frozen['usage']['unsettled']:raise BudgetStop('unsettled_previous_request')
    batch=Path(batch).resolve();providers=credentials(provider_config);cfg=config_for(batch,providers['coco']);secrets=tuple(p['api_key'] for p in providers.values());ledger=Ledger(batch/'private/requests.sqlite',plan_hash());box={}
    def meta(key):
        with ledger.connect() as db:
            row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();return row[0] if row else None
    def verify():
        try:
            verify_frozen(batch,provider_config)
            if 'app' in box:
                if box['app'].runtime.cleanup_uncertain or box['app'].runtime.event_store.workspace_uncertain():raise BudgetStop('uncertain_runtime')
        except Exception:
            ledger.halt('frozen_or_runtime_integrity_changed');raise BudgetStop('frozen_or_runtime_integrity_changed') from None
    ledger.verify=verify
    def observe(rid,purpose,request,response):
        try:
            c=box['app'].runtime.conversations[box['app'].runtime.owner]
            choice=response.choices[0]
            private_json(batch/'private'/f'{case}-usage-{rid:02}.json',dict(reservation=rid,usage=usage_values(getattr(response,'usage',None)),finish_reason=choice.finish_reason))
            if getattr(choice.message,'tool_calls',None):raise BudgetStop('unexpected_tool_call')
            data=inclusion(request);data.update(case=case,reservation=rid,purpose=purpose,finish_reason=choice.finish_reason,reply=redact(choice.message.content,secrets),source_preservation=preservation(case,c.history,c.session,request,c.resources.get('context')))
            private_json(batch/'private'/f'{case}-request-{rid:02}.json',data)
            if data['source_preservation']['unknown']:raise BudgetStop('source_measurement_unknown')
        except Exception:
            ledger.halt('tool_or_evidence_integrity_failure');raise
    def wrap(settings):return BudgetClient(build_client(settings).with_options(max_retries=0),settings,ledger,case,observe)
    def factory(settings):
        require_authorization(authorization)
        backup=replace(settings,provider='coco2',**{k:providers['coco2'][k] for k in ('model','base_url','api_key')})
        return ProviderFailoverClient(wrap(settings),settings,backup,wrap)
    app=create_app(cfg,port=port,client_factory=factory);box['app']=app;original_start=app.runtime.start;original_pin=app.runtime.pin;original_lifespan=app.app.router.lifespan_context
    def validate_pins(c,expected):
        actual=c.history.pins.list(active_only=True)
        if sorted(p['content'] for p in actual)!=sorted(expected):raise BudgetStop('unexpected_active_pins')
        for p in c.history.pins.list():
            spec=next((s for s in pins(case) if s['content']==p['content']),None)
            if spec is None or spec['source_span']!=p['source_span']:raise BudgetStop('unregistered_pin_or_span')
            with c.history.store.connection() as db:
                row=db.execute("SELECT role,content FROM messages WHERE id=? AND session_id=?",(p['source_message_id'],c.id)).fetchone()
                if row is None or row['role']!='user' or row['content']!=MESSAGES[case][spec['source_turn']-1]:raise BudgetStop('pin_source_changed')
    def pin(c,value):
        try:
            ledger.verify();n=int(meta('input_'+case) or 0)
            if case=='S03':allowed=PIN_TEXT[case] if n==1 else []
            else:allowed=[PIN_TEXT[case][n-1]] if n in (1,2) else []
            with c.history.store.connection() as db:
                row=db.execute("SELECT content FROM messages WHERE id=? AND session_id=? AND role='user'",(value.get('message_id'),c.id)).fetchone()
            if row is None or type(value.get('start')) is not int or type(value.get('end')) is not int:raise BudgetStop('pin_source_invalid')
            text=row['content'][value['start']:value['end']]
            if text not in allowed:raise BudgetStop('unregistered_pin_operation')
            spec=next(s for s in pins(case) if s['content']==text)
            if row['content']!=MESSAGES[case][spec['source_turn']-1] or [value['start'],value['end']]!=spec['source_span']:raise BudgetStop('pin_source_invalid')
            active=c.history.pins.list(active_only=True)
            if any(p['content']==text for p in active):raise BudgetStop('duplicate_pin')
            if case=='S03' and (len(active)>=2 or text!=PIN_TEXT[case][len(active)]):raise BudgetStop('registered_pin_order_required')
            if case!='S03' and n==2:
                if len(active)!=1 or value.get('replace_id')!=active[0]['id'] or value.get('expected_revision')!=active[0]['revision']:raise BudgetStop('registered_replacement_required')
            elif value.get('replace_id'):raise BudgetStop('unexpected_replacement')
            return original_pin(c,value)
        except Exception:
            ledger.halt('pin_operation_integrity');raise
    app.runtime.pin=pin
    async def start(c,text):
        try:
            ledger.verify()
            if app.runtime.owner is not None:return False
            index=int(meta('input_'+case) or 0)
            if index>=len(MESSAGES[case]) or text!=MESSAGES[case][index]:raise BudgetStop('unregistered_message')
            sid=meta('session_'+case)
            if sid and c.id!=sid:raise BudgetStop('wrong_session')
            if not sid and (c.messages or c.id in [meta('session_'+x) for x in LIMITS if x!=case]):raise BudgetStop('new_independent_session_required')
            validate_pins(c,expected_active(case,index))
            with ledger.connect() as db:
                db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('session_'+case,c.id));db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('input_'+case,str(index+1)))
            began=time.monotonic();accepted=await original_start(c,text)
            if not accepted:raise BudgetStop('turn_start_refused')
        except Exception:
            ledger.halt('input_or_pin_integrity');raise
        def settled(task):
            try:
                ledger.verify()
                private_json(batch/'private'/f'{case}-turn-{index+1:02}.json',dict(session_id=c.id,status=c.status,elapsed_seconds=time.monotonic()-began,resources=c.resources,pin_budget=c.pin_budget,event_count=c.history.store.query('SELECT count(*) AS n FROM events WHERE session_id=?',(c.id,))[0]['n'],workspace_unchanged=True))
            except Exception:
                ledger.halt('settlement_or_integrity_failure');app.runtime.cleanup_uncertain=True
        c.task.add_done_callback(settled);return True
    app.runtime.start=start
    @asynccontextmanager
    async def lifespan(application):
        ledger.verify();ledger.start(case)
        async with original_lifespan(application):
            try:yield
            finally:
                for c in app.runtime.conversations.values():await app.runtime.stop(c)
                ledger.verify()
                if int(meta('input_'+case) or 0)!=len(MESSAGES[case]):ledger.halt('case_incomplete_no_rerun')
                sid=meta('session_'+case)
                if sid:validate_pins(app.runtime.conversations[sid],PIN_TEXT[case] if case=='S03' else [] if case=='S02' else PIN_TEXT[case][1:])
                private_json(batch/'private'/f'{case}-shutdown.json',dict(case=case,ledger_count=len(ledger.rows()),workspace_hashes=fingerprint(cfg.workspace),uncertain=app.runtime.cleanup_uncertain))
        ledger.finish(case)
    app.app.router.lifespan_context=lifespan;app.uat_ledger=ledger
    return app

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=list(LIMITS),required=True);p.add_argument('--batch',type=Path,default=BATCH);p.add_argument('--provider-config',type=Path,required=True);p.add_argument('--authorization',default=AUTHORIZATION);p.add_argument('--port',type=int,default=PORT);a=p.parse_args()
    require_authorization(a.authorization)
    uvicorn.run(make_app(a.case,a.batch,a.provider_config,authorization=a.authorization,port=a.port),host='127.0.0.1',port=a.port,access_log=False,log_level='warning')
if __name__=='__main__':main()
