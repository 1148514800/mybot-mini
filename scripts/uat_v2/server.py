"""Existing Web runtime with bounded v2 adapter; default NOT_GRANTED, zero dispatch."""
import argparse,asyncio,hashlib,json,tempfile,time,os
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from mybot.web.server import create_app
from mybot.web.security import redact
from mybot.provider_failover import build_gateway_client
from mybot.storage.session_store import validate_turns
from scripts.uat.server import credentials,private_json
from .budget import Ledger,BudgetClient,BudgetStop,LIMITS
from .plan import config_for,plan_hash,LIVE_AUTHORIZATION
from .prepare import verify_frozen
from .preflight import require_environment
from .fixtures import fingerprint,create
from .calibrate import PROVIDER


def require_authorization(value):
    if value!='GRANTED_34_REQUESTS':raise BudgetStop('live_authorization_not_granted')


def make_app(case,batch,provider_config,*,authorization=LIVE_AUTHORIZATION,port=8881):
    require_authorization(authorization)  # BEFORE credentials, ledger mutation or SDK creation.
    verify_frozen(batch,provider_config)
    batch=Path(batch).resolve();root=batch/'workspaces'/case
    prepared=json.loads((batch/'prepared.json').read_text())
    if fingerprint(root)!=prepared['fixtures'][case]:raise BudgetStop('fixture_changed_before_case')
    providers=credentials(provider_config);cfg=config_for(case,root,providers['coco'])
    ledger=Ledger(batch/'requests.sqlite',plan_hash());private=batch/'private';private.mkdir(mode=0o700,exist_ok=True)
    if any(r['state']=='reserved' for r in ledger.rows()):raise BudgetStop('unsettled_previous_request')
    secrets=tuple(p['api_key'] for p in providers.values())
    def observe(reservation,purpose,request,response):
        choice=response.choices[0];message=choice.message
        value=dict(purpose=purpose,finish_reason=choice.finish_reason,reply=redact(message.content,secrets),
                   tools=[c.function.name for c in message.tool_calls or []],
                   # Private exact cited views support later semantic auditing; never publish full conversations.
                   context_messages=[dict(role=m['role'],content=redact(m.get('content'),secrets)) for m in request['messages']] if case=='T03' else None)
        private_json(private/f'{case}-response-{reservation:02}.json',value)
    def factory(settings):
        require_authorization(authorization)
        settings.providers=providers
        gateway=build_gateway_client(settings)
        gateway._primary=BudgetClient(gateway._primary,settings,ledger,case,observe)
        original=gateway._factory
        gateway._factory=lambda backup:BudgetClient(original(backup),backup,ledger,case,observe)
        return gateway
    app=create_app(cfg,port=port,client_factory=factory,approval_timeout=180,task_timeout=900)
    app.uat_ledger=ledger;saved={}
    def event_sink(event):
        try:
            fd=os.open(private/f'{case}-activity.jsonl',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
            with os.fdopen(fd,'a') as stream:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
        except OSError:
            ledger.halt('activity_evidence_write_failed')
            asyncio.current_task().cancel()
            raise
    bind_task_contract(app,case,event_sink=event_sink)
    async def monitor():
        try:
            while not app.runtime.closed:
                for c in app.runtime.conversations.values():
                    if c.task is None or not c.task.done() or saved.get(c.id)==c.sequence:continue
                    saved[c.id]=c.sequence;turns=c.session.export_turns();validate_turns(turns)
                    state=c.state();state.pop('approval',None)
                    private_json(private/f'{case}-turn-{len(turns):02}.json',dict(state=state,
                        session=dict(turns=len(turns),user_hashes=[hashlib.sha256(m['content'].encode()).hexdigest() for t in turns for m in t if m['role']=='user'],
                                     valid_pairs=True,contains_summary=any('低信任历史参考：模型选择' in (m.get('content') or '') for t in turns for m in t)),
                        approvals=c.approval.audit if c.approval else [],workspace_hashes=fingerprint(root)))
                    if app.runtime.cleanup_uncertain:ledger.halt('cleanup_uncertain')
                await asyncio.sleep(.1)
        except asyncio.CancelledError:
            raise
        except Exception:
            ledger.halt('observation_failed')
            app.runtime.cleanup_uncertain=True
            for conversation in app.runtime.conversations.values():
                if conversation.task is not None:conversation.task.cancel()
            raise
    original_lifespan=app.app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        await require_environment(case,root)
        ledger.start(case)
        async with original_lifespan(application):
            watcher=asyncio.create_task(monitor())
            try:yield
            finally:
                await monitor_once_on_exit(app,case,private,root)
                watcher.cancel();await asyncio.gather(watcher,return_exceptions=True)
        if app.runtime.cleanup_uncertain:ledger.halt('cleanup_uncertain')
        ledger.finish(case)
    app.app.router.lifespan_context=lifespan
    return app


async def monitor_once_on_exit(app,case,private,root):
    # Preserve the final safe state, including cancellation/cleanup outcome.
    for c in app.runtime.conversations.values():
        await app.runtime.stop(c)
        state=c.state();state.pop('approval',None)
        private_json(private/f'{case}-final.json',dict(state=state,approvals=c.approval.audit if c.approval else [],workspace_hashes=fingerprint(root)))


def preview_app(case,root,port):
    from .synthetic import SyntheticClient
    from dataclasses import replace
    cfg=replace(config_for(case,root,PROVIDER),provider='offline-synthetic',model='OFFLINE-SYNTHETIC-v2')
    app=create_app(cfg,port=port,client_factory=lambda settings:SyntheticClient(settings,case),approval_timeout=180)
    return app


def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=list(LIMITS),required=True);p.add_argument('--preview',action='store_true');p.add_argument('--batch');p.add_argument('--provider-config');p.add_argument('--port',type=int,default=8881);p.add_argument('--authorization',default=LIVE_AUTHORIZATION);a=p.parse_args()
    if a.preview:
        with tempfile.TemporaryDirectory(prefix='uat-v2-OFFLINE-SYNTHETIC-') as folder:
            root=Path(folder).resolve()/a.case;create(a.case,root)
            uvicorn.run(preview_app(a.case,root,a.port),host='127.0.0.1',port=a.port,access_log=False,log_level='warning')
    else:
        require_authorization(a.authorization)
        if not a.batch or not a.provider_config:p.error('live needs frozen batch and provider configuration')
        uvicorn.run(make_app(a.case,a.batch,a.provider_config,authorization=a.authorization,port=a.port),host='127.0.0.1',port=a.port,access_log=False,log_level='warning')


def bind_task_contract(app,case,*,event_sink=None):
    """One conversation and exact preregistered turns, after native CSRF checks."""
    from starlette.routing import request_response
    from starlette.responses import JSONResponse
    from .plan import MESSAGES
    for route in app.app.routes:
        if route.path == '/api/conversations/{id}/clear':
            async def no_clear(request):return JSONResponse({'error':'frozen_attempt_cannot_clear'},status_code=409)
            route.app=request_response(no_clear)
        if route.path == '/api/conversations':
            original=route.endpoint
            async def one_conversation(request,_original=original):
                if app.runtime.conversations:return JSONResponse({'error':'one_attempt_only'},status_code=409)
                result=await _original(request)
                if event_sink is not None:
                    for conversation in app.runtime.conversations.values():
                        emit=conversation.emit
                        def observed(event,_emit=emit,_conversation=conversation):
                            _emit(event)
                            # Store the already bounded/redacted event, never raw callback data.
                            event_sink(dict(_conversation.events[-1]))
                        conversation.emit=observed
                return result
            route.app=request_response(one_conversation)
        if route.path == '/api/conversations/{id}/messages':
            original=route.endpoint
            async def exact_message(request,_original=original):
                try:body=await request.json()
                except Exception:return JSONResponse({'error':'invalid_task_message'},status_code=400)
                if not isinstance(body,dict):return JSONResponse({'error':'invalid_task_message'},status_code=400)
                c=app.runtime.conversations.get(request.path_params['id'])
                if c is None:return await _original(request)
                index=sum(m['role']=='user' for m in c.messages)
                if index>=len(MESSAGES[case]) or body.get('message')!=MESSAGES[case][index]:
                    return JSONResponse({'error':'frozen_message_required'},status_code=409)
                if index and c.status!='completed':return JSONResponse({'error':'no_retry_after_failed_turn'},status_code=409)
                return await _original(request)
            route.app=request_response(exact_message)

if __name__=='__main__':main()
