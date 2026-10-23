"""OFFLINE/SYNTHETIC end-to-end evidence, zero provider requests.

--serve-diagnostics starts a disposable real HTTP/SSE browser target. Its only
fault injection is native patch metadata rejection; never a real UAT attempt.
"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.check_patch_preview_receipt import synthetic_case
from scripts import check_patch_diagnostics as diagnostics
from scripts import check_adaptive_compaction as adaptive

class EndToEndChecks(unittest.IsolatedAsyncioTestCase):
    async def test_single_file_receipt_unittest_current_revision(self):
        row=await synthetic_case('receipt','normal')
        self.assertTrue(row['synthetic_contract_success']);self.assertEqual(row['controller_verified'],1)
        self.assertTrue(row['tool_ids_paired']);self.assertEqual(row['actual_http_requests'],0)
    async def test_cross_file_publication_current_revision(self):
        row=await synthetic_case('receipt','multi_file')
        self.assertTrue(row['synthetic_contract_success']);self.assertEqual(row['controller_verified'],1)
        self.assertEqual(row['patch_committed'],1)


class WebCompactionChecks(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=diagnostics.DiagnosticChecks.asyncSetUp
    post=diagnostics.DiagnosticChecks.post
    new=diagnostics.DiagnosticChecks.new
    run_chat=diagnostics.DiagnosticChecks.run_chat
    async def long_chat(self, room):
        from scripts.modernization_fixtures import Base, Client
        from dataclasses import replace
        check=Base();check.setUp();self.addCleanup(check.doCleanups)
        check.semantic();cfg=replace(check.config,workspace=self.root,context_summary_max_chars=room)
        client=Client();self.app.runtime.config=cfg;self.app.runtime.client_factory=lambda _:client
        identifier=await self.new();conv=self.app.runtime.conversations[identifier]
        history=check.history();conv.session.restore(history)
        state=await self.run_chat('OFFLINE/SYNTHETIC 继续',identifier)
        self.assertEqual(conv.session.export_turns()[:-1],history)
        self.assertEqual(state['status'],'completed')
        return state,client,cfg
    async def test_web_long_conversation_applied_and_cli_agrees(self):
        state,client,cfg=await self.long_chat(3000)
        context=state['resources']['context'];self.assertEqual(context['context_compaction_status'],'semantic_applied')
        self.assertEqual(state['resources']['compaction_requests'],1)
        self.assertLessEqual(context['estimated_input_tokens'],context['input_token_limit'])
        from scripts.modernization_fixtures import Client, Base
        from mybot.agent import AgentLoop,ContextBuilder
        from mybot.tools import build_default_tool_registry
        cli=AgentLoop(Client(),cfg,build_default_tool_registry(self.root),ContextBuilder(self.root))
        cli.session.restore(Base.history(self));await cli.handle_message('OFFLINE/SYNTHETIC 继续')
        self.assertEqual(cli.resources.context['context_compaction_status'],context['context_compaction_status'])
        self.assertEqual(cli.resources.context['estimated_input_tokens'],context['estimated_input_tokens'])
    async def test_web_insufficient_room_zero_summary_requests(self):
        state,client,_=await self.long_chat(128)
        self.assertEqual(state['resources']['context']['context_compaction_status'],'semantic_skipped_insufficient_room')
        self.assertEqual(state['resources']['compaction_requests'],0);self.assertEqual(len(client.requests),1)
    async def test_real_network_sse_failure_diagnostics(self):
        import socket,httpx,uvicorn
        from scripts.check_web_ui import config,SyntheticClient
        from mybot.web.server import create_app
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();port=sock.getsockname()[1]
        app=create_app(config(self.root,True),port=port,client_factory=SyntheticClient)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False,lifespan='off'))
        task=asyncio.create_task(server.serve(sockets=[sock]))
        try:
            for _ in range(100):
                if server.started:break
                await asyncio.sleep(.01)
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}') as http:
                await http.get('/');boot=(await http.get('/api/bootstrap')).json()
                headers={'Origin':f'http://127.0.0.1:{port}','X-Mybot-CSRF':boot['csrf']}
                identifier=(await http.post('/api/conversations',json={},headers=headers)).json()['id']
                with patch('mybot.tools.patch.check_metadata',side_effect=ValueError('unsupported_ownership')):
                    await http.post(f'/api/conversations/{identifier}/messages',json={'message':'OFFLINE/SYNTHETIC 修复'},headers=headers)
                    await app.runtime.conversations[identifier].task
                async with http.stream('GET',f'/api/conversations/{identifier}/events') as stream:
                    data=[]
                    async for line in stream.aiter_lines():
                        if line.startswith('data: '):
                            data.append(json.loads(line[6:]))
                            if data[-1]['type'] in ('message_completed', 'message_failed'):break
                event=next(e for e in data if e['type']=='tool_finished' and e['tool']=='apply_patch')
                self.assertEqual(event['metadata']['safe_error_code'],'unsupported_ownership')
                self.assertEqual(app.runtime.conversations[identifier].status,'failed')
                self.assertNotIn('preview_receipt',json.dumps(data));self.assertNotIn(str(self.root),json.dumps(data))
        finally:
            server.should_exit=True;await task;await app.runtime.close()


async def export_comparison(path):
    rows=[await synthetic_case('receipt',s) for s in ('normal','multi_file','metadata','publication_uncertain')]
    from scripts.modernization_fixtures import Base
    from mybot.agent.context_compactor import ContextCompactor, FIELDS, LABEL
    from mybot.agent.context_manager import ContextManager
    from scripts.check_session import response
    import copy
    check=Base();check.setUp()
    try:
        check.semantic();before=copy.deepcopy(check.agent.session.export_turns())
        await check.agent.handle_message('OFFLINE/SYNTHETIC 继续')
        context=dict(check.agent.resources.context)
        applied=dict(status=context['context_compaction_status'],
            available_summary_budget=context['available_summary_budget'],
            estimated_input_tokens=context['estimated_input_tokens'],input_limit=context['input_token_limit'],
            dynamic_max_tokens=check.client.requests[0]['max_tokens'],
            model_requests=len(check.client.requests),summary_requests=check.agent.resources.compaction_requests,
            canonical_preserved=before==check.agent.session.export_turns()[:-1])
        check.semantic();check.config.context_summary_max_chars=128
        await check.agent.handle_message('OFFLINE/SYNTHETIC 继续')
        skipped=dict(status=check.agent.resources.context['context_compaction_status'],
            model_requests=len(check.client.requests)-applied['model_requests'],
            summary_requests=check.agent.resources.compaction_requests)
        cfg=check.config;cfg.context_token_budget['mode']='legacy_chars';cfg.context_max_chars=1500;cfg.context_summary_max_chars=3000
        manager=ContextManager(cfg);base=[dict(role='system',content='rules'),dict(role='user',content='current')]
        doc={k:[] for k in FIELDS};doc['user_constraints']=[dict(turn=1,message=0,quote='不删除用户文件')]
        doc['important_artifacts']=[dict(turn=1,message=0,quote='x'*500) for _ in range(4)]
        selected={k:[{**e,'source_role':'user','evidence_status':'historical_report_not_current_verification'} for e in v] for k,v in doc.items()}
        raw=dict(role='assistant',content=LABEL+json.dumps(selected,ensure_ascii=False))
        fits=lambda item:manager.accepts(base[:1]+[item]+base[1:],None)
        calls=[]
        async def invoke(request):calls.append(request);return response(json.dumps(doc,ensure_ascii=False))
        summary,status=await ContextCompactor(cfg).compact(check.history(),cfg,invoke,
            available_summary_budget=manager.summary_budget(base,None),fits=fits)
        pruning=dict(unpruned_fits=fits(raw),status=status,pruned_fits=bool(summary and fits(summary)),
            summary_requests=len(calls),constraint_retained=bool(summary and '不删除用户文件' in summary['content']))
        Path(path).write_text(json.dumps(dict(mode='OFFLINE/SYNTHETIC',real_model_api_requests=0,
            original_uat_regraded=False,patch_cases=rows,
            semantic_comparison=dict(historical_live=dict(attempts=2,applied=0,reported_tokens=6452,unchanged=True),
                new_synthetic=dict(applied=applied,skipped=skipped,pruning=pruning),
                comparable_model_success_rate=False)),ensure_ascii=False,indent=2)+'\n')
    finally:check.doCleanups()



def serve():
    from scripts.check_web_ui import config,SyntheticClient
    from scripts.check_patch_preview_receipt import init
    from mybot.web.server import create_app
    import uvicorn
    with tempfile.TemporaryDirectory(prefix='mybot-OFFLINE-SYNTHETIC-') as folder:
        root=Path(folder).resolve();init(root)
        app=create_app(config(root,True),port=8879,client_factory=SyntheticClient)
        with patch('mybot.tools.patch.check_metadata',side_effect=ValueError('unsupported_ownership')):
            uvicorn.run(app,host='127.0.0.1',port=8879,access_log=False,log_level='warning')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--serve-diagnostics',action='store_true');parser.add_argument('--comparison');args,rest=parser.parse_known_args()
    if args.serve_diagnostics:serve()
    elif args.comparison:asyncio.run(export_comparison(args.comparison))
    else:unittest.main(argv=[__file__,*rest],verbosity=2)
