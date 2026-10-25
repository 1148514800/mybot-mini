"""Opt-in adapter around unchanged create_app/ChatRuntime/AgentLoop. No auto Live."""
import argparse,asyncio,json,time
from contextlib import asynccontextmanager
from pathlib import Path
from dataclasses import replace
import uvicorn
from mybot.web.server import create_app
from mybot.web.security import redact
from mybot.config import build_client
from mybot.provider_failover import ProviderFailoverClient
from scripts.uat.server import credentials,private_json
from .budget import Ledger,BudgetClient,BudgetStop
from .plan import LIVE_AUTHORIZATION,LIMITS,MESSAGES,PINS,OLD,NEW,BATCH,config_for,plan_hash,span
from .prepare import verify_frozen,fingerprint
from .evidence import inclusion,information_loss


def require_authorization(value):
    if value!='GRANTED_16_REQUESTS':raise BudgetStop('live_authorization_not_granted')


def make_app(case,batch,provider_config,*,authorization=LIVE_AUTHORIZATION,port=8889):
    require_authorization(authorization) # Must precede credentials, mutation and any SDK construction.
    if case not in LIMITS:raise BudgetStop('unknown_case')
    verify_frozen(batch,provider_config);batch=Path(batch).resolve();providers=credentials(provider_config)
    ledger=Ledger(batch/'private/requests.sqlite',plan_hash());box={}
    def verify():
        try:
            verify_frozen(batch,provider_config)
            if 'app' in box:
                with box['app'].runtime.event_store.connection() as db:
                    if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise BudgetStop('event_database_corrupt')
        except Exception:
            ledger.halt('frozen_environment_changed');raise BudgetStop('frozen_environment_changed') from None
    ledger.verify=verify
    if any(r['state']=='reserved' for r in ledger.rows()):raise BudgetStop('unsettled_previous_request')
    cfg=config_for(batch,providers['coco']);secrets=tuple(v['api_key'] for v in providers.values())
    def current():
        runtime=box['app'].runtime
        return runtime.conversations.get(runtime.owner)
    def observe(rid,purpose,request,response):
        c=current();data=inclusion(request)
        choice=response.choices[0]
        data.update(case=case,reservation=rid,purpose=purpose,finish_reason=choice.finish_reason,
            reply=redact(choice.message.content,secrets),information_loss=information_loss(c.history,c.session.export_turns()))
        try:private_json(batch/'private'/f'{case}-request-{rid:02}.json',data)
        except Exception:
            ledger.halt('evidence_write_failed');raise BudgetStop('evidence_write_failed') from None
    def wrap(settings):
        return BudgetClient(build_client(settings).with_options(max_retries=0),settings,ledger,case,observe)
    def factory(settings):
        require_authorization(authorization)
        backup=replace(settings,provider='coco2',**{k:providers['coco2'][k] for k in ('api_key','base_url','model')})
        return ProviderFailoverClient(wrap(settings),settings,backup,wrap)
    app=create_app(cfg,port=port,client_factory=factory);box['app']=app;original_start=app.runtime.start
    original_lifespan=app.app.router.lifespan_context
    def meta(key):
        with ledger.connect() as db:
            row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();return row[0] if row else None
    async def start(c,text):
        ledger.verify()
        if app.runtime.cleanup_uncertain:
            ledger.halt('cleanup_uncertain');raise BudgetStop('cleanup_uncertain')
        if app.runtime.owner is not None:return False
        index=int(meta('input_'+case) or 0)
        if index>=len(MESSAGES[case]) or text!=MESSAGES[case][index]:ledger.halt('unregistered_message');raise BudgetStop('unregistered_message')
        sid=meta('session_'+case)
        if case=='L03':sid=meta('session_L01')
        if sid and c.id!=sid:ledger.halt('wrong_session');raise BudgetStop('wrong_session')
        if not sid and (c.messages or case=='L02' and c.id==meta('session_L01')):raise BudgetStop('new_session_required')
        expected=PINS if case=='L03' or case=='L01' and index>0 else [OLD] if case=='L02' and index==1 else [NEW] if case=='L02' and index==2 else []
        pins=c.history.pins.list(active_only=True)
        if sorted(p['content'] for p in pins)!=sorted(expected):ledger.halt('unexpected_active_pins');raise BudgetStop('unexpected_active_pins')
        for p in pins:
            source=MESSAGES['L01'][0] if case in ('L01','L03') else MESSAGES['L02'][0 if p['content']==OLD else 1]
            if p['source_span']!=span(source,p['content']):raise BudgetStop('pin_span_changed')
            with c.history.store.connection() as db:
                row=db.execute('SELECT role,content FROM messages WHERE id=? AND session_id=?',(p['source_message_id'],c.id)).fetchone()
                if row is None or row['role']!='user' or row['content']!=source:raise BudgetStop('pin_source_changed')
        with ledger.connect() as db:
            db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)",('session_'+case,c.id))
            db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)",('input_'+case,str(index+1)))
        began=time.monotonic()
        try:accepted=await original_start(c,text)
        except BaseException:
            ledger.halt('turn_start_failed');raise
        if not accepted:
            ledger.halt('turn_start_refused');raise BudgetStop('turn_start_refused')
        def settled(task):
            try:
                ledger.verify()
                if app.runtime.cleanup_uncertain:ledger.halt('cleanup_uncertain')
                private_json(batch/'private'/f'{case}-turn-{index+1:02}.json',dict(session_id=c.id,status=c.status,web_task_elapsed_seconds=time.monotonic()-began,resources=c.resources,pin_budget=c.pin_budget,
                    event_db_bytes=cfg.session_event_path.stat().st_size,event_count=c.history.store.query('SELECT count(*) AS n FROM events WHERE session_id=?',(c.id,))[0]['n'],workspace_unchanged=True))
            except Exception:
                ledger.halt('settlement_or_integrity_failed');app.runtime.cleanup_uncertain=True
        c.task.add_done_callback(settled)
        return True
    app.runtime.start=start
    @asynccontextmanager
    async def lifespan(application):
        ledger.verify();ledger.start(case)
        async with original_lifespan(application):
            try:yield
            finally:
                for c in app.runtime.conversations.values():await app.runtime.stop(c)
                ledger.verify()
                states=[]
                for c in app.runtime.conversations.values():
                    status=c.history.status();states.append(dict(session_id=c.id,title=c.title,status=status['status'],pin_count=len(c.history.pins.list(active_only=True)),message_count=len(c.history.messages()),event_count=c.history.store.query('SELECT count(*) AS n FROM events WHERE session_id=?',(c.id,))[0]['n'],turn_id=status['turn_id'],approval_present=c.approval.public_pending() is not None if c.approval else False,report=c.report))
                private_json(batch/'private'/f'{case}-shutdown.json',dict(sessions=states,ledger_reservations=len(ledger.rows()),workspace_hashes=fingerprint(cfg.workspace),event_db_bytes=cfg.session_event_path.stat().st_size))
                if app.runtime.cleanup_uncertain:ledger.halt('cleanup_uncertain')
        ledger.finish(case)
    app.app.router.lifespan_context=lifespan;app.uat_ledger=ledger
    return app

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=list(LIMITS),required=True);p.add_argument('--batch',type=Path,default=BATCH);p.add_argument('--provider-config',type=Path,required=True);p.add_argument('--authorization',default=LIVE_AUTHORIZATION);p.add_argument('--port',type=int,default=8889);a=p.parse_args()
    require_authorization(a.authorization)
    uvicorn.run(make_app(a.case,a.batch,a.provider_config,authorization=a.authorization,port=a.port),host='127.0.0.1',port=a.port,access_log=False,log_level='warning')
if __name__=='__main__':main()
