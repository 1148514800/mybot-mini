"""Real Web UAT entry. Reads credentials in memory; only UAT adapter code is added."""
from __future__ import annotations
import argparse,asyncio,hashlib,json,os,time
from dataclasses import replace
from pathlib import Path
import uvicorn
from mybot.web.server import create_app
from mybot.web.security import redact
from mybot.provider_failover import build_gateway_client
from mybot.storage.session_store import validate_turns
from .budget import Ledger,BudgetClient,BudgetStop
from .plan import config_for,plan_hash
from .fixtures import fingerprint


def private_json(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    os.chmod(temporary,0o600);temporary.replace(path)

def credentials(path):
    config=json.loads(Path(path).read_text());llm=config['llm'];providers=llm['providers']
    if llm['provider']!='coco':raise BudgetStop('unexpected_primary_provider')
    for name,model in [('coco','deepseek-v4.1-flash'),('coco2','glm-5.3-flash')]:
        p=providers[name]
        if p['model']!=model or not p['api_key'] or p['api_key'].startswith('YOUR_'):raise BudgetStop('missing_or_changed_provider')
    return {k:providers[k] for k in ('coco','coco2')}


def make_app(case,batch,config_path,port=8878,preview=False):
    batch=Path(batch).resolve();batch.mkdir(mode=0o700,parents=True,exist_ok=True)
    root=batch/'workspaces'/case
    if not root.is_dir():raise BudgetStop('fixture_not_prepared')
    if not preview:
        frozen=json.loads((batch/'freeze.json').read_text())
        if frozen['plan_hash']!=plan_hash():raise BudgetStop('frozen_plan_changed')
        for name,digest in frozen['source_hashes'].items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise BudgetStop('frozen_source_changed')
        if hashlib.sha256(Path(config_path).read_bytes()).hexdigest()!=frozen['provider_config_sha256']:raise BudgetStop('provider_config_changed')
        info=(batch/'requests.sqlite').stat()
        if [info.st_dev,info.st_ino]!=frozen['ledger_identity']:raise BudgetStop('ledger_replaced')
        prepared=json.loads((batch/'prepared.json').read_text())
        if fingerprint(root)!=prepared['fixtures'][case]['before']:raise BudgetStop('fixture_changed_before_case')
    providers=credentials(config_path) if not preview else {'coco':dict(model='deepseek-v4.1-flash',api_key='synthetic-preview',base_url='https://offline.invalid/v1')}
    config=config_for(case,root,providers['coco'])
    ledger=Ledger(batch/'requests.sqlite',plan_hash())
    secrets=tuple(v['api_key'] for v in providers.values())
    private=batch/'private';private.mkdir(mode=0o700,exist_ok=True)
    def observe(reservation,purpose,request,response):
        message=response.choices[0].message
        # This local private evidence is never copied wholesale into the report.
        body={'purpose':purpose,'reply':redact(message.content,secrets),'finish_reason':response.choices[0].finish_reason,
              'tools':[c.function.name for c in message.tool_calls or []],
              'context_messages':[{'role':m['role'],'content':redact(m.get('content'),secrets)} for m in request['messages']] if case=='U06' else None}
        private_json(private/f'{case}-response-{reservation:02}.json',body)
    def factory(settings):
        if preview:raise BudgetStop('preview_cannot_send_models')
        settings.providers=providers  # memory-only load, same official gateway builder
        gateway=build_gateway_client(settings)
        gateway._primary=BudgetClient(gateway._primary,settings,ledger,case,observe)
        original=gateway._factory
        gateway._factory=lambda backup:BudgetClient(original(backup),backup,ledger,case,observe)
        return gateway
    app=create_app(config,port=port,client_factory=factory,approval_timeout=180,task_timeout=900)
    app.uat_ledger=ledger
    if not preview:
        if any(r['state']=='reserved' for r in ledger.rows()):raise BudgetStop('unsettled_previous_request')
        ledger.start(case)
    saved={}
    async def monitor():
        while not app.runtime.closed:
            for c in app.runtime.conversations.values():
                if c.task is None or not c.task.done():continue
                users=[m['content'] for m in c.messages if m['role']=='user']
                key=(c.id,len(users),c.sequence)
                if saved.get(c.id)==key:continue
                saved[c.id]=key
                turns=c.session.export_turns()
                try:validate_turns(turns);valid=True
                except Exception:valid=False
                value={'case':case,'conversation':c.id,'time':time.time(),'state':c.state(),
                    'session':{'turn_count':len(turns),'valid_pairs':valid,'user_hashes':[hashlib.sha256(m['content'].encode()).hexdigest() for t in turns for m in t if m['role']=='user'],
                               'contains_semantic_summary':any('低信任历史参考：模型选择' in (m.get('content') or '') for t in turns for m in t)},
                    'approval_audit':c.approval.audit if c.approval else [],'workspace_hashes':fingerprint(root)}
                value['state'].pop('approval',None)
                private_json(private/f'{case}-turn-{len(users):02}.json',value)
            await asyncio.sleep(.2)
    core=app.app
    old_lifespan=core.router.lifespan_context
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def lifespan(application):
        if not preview and case in ('U03','U04','U05'):
            from .check_environment import require_environment
            await require_environment(case, root)
        async with old_lifespan(application):
            watcher=asyncio.create_task(monitor())
            try:yield
            finally:
                watcher.cancel()
                await asyncio.gather(watcher,return_exceptions=True)
        if not preview:
            if app.runtime.cleanup_uncertain:ledger.halt('cleanup_uncertain')
            ledger.finish(case)
    core.router.lifespan_context=lifespan
    return app


def main():
    p=argparse.ArgumentParser();p.add_argument('--case',required=True,choices=['U01','U02','U03','U04','U05','U06']);p.add_argument('--batch',required=True);p.add_argument('--provider-config',required=True);p.add_argument('--port',type=int,default=8878);p.add_argument('--preview',action='store_true');p.add_argument('--confirm-live-cost',action='store_true');args=p.parse_args()
    if not args.preview and not args.confirm_live_cost:p.error('live requires explicit cost confirmation')
    app=make_app(args.case,args.batch,args.provider_config,args.port,args.preview)
    uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning')
if __name__=='__main__':main()
