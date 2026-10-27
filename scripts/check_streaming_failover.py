import asyncio,json,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import httpx
from openai import AsyncOpenAI,APIConnectionError
from mybot.runtime_accounting import RuntimeAccounting,response_status
from mybot.provider_failover import ProviderFailoverClient,FallbackBudgetExceeded
from mybot.agent.token_counter import TokenBudgetError
from scripts.eventstore_fixtures import configuration
from scripts.streaming_fixtures import Client,Stream,chunk

class FailoverStreamChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.cfg=configuration(Path(self.tmp.name).resolve(),provider='coco',context_token_budget={'mode':'estimate','input_limit':20000});self.backup=replace(self.cfg,provider='coco2',model='backup');self.req=dict(model=self.cfg.model,messages=[dict(role='user',content='test')],tools=None,max_tokens=100,stream=True)
    def gateway(self,packets):
        self.primary=Client([Stream(packets)]);self.back=Client([Stream([chunk('backup',finish='stop')])]);return ProviderFailoverClient(self.primary,self.cfg,self.backup,lambda _:self.back)
    async def test_primary_success_count_once(self):
        g=self.gateway([chunk('primary',finish='stop')]);a=RuntimeAccounting();await a.request(g,self.cfg,self.req);self.assertEqual(len(a.records),1);self.assertTrue(a.records[0]['first_chunk_received']);self.assertEqual(self.back.requests,[])
    async def test_error_before_first_chunk_fallback(self):
        g=self.gateway([APIConnectionError(request=httpx.Request('POST','http://mock.invalid'))]);a=RuntimeAccounting();r=await a.request(g,self.cfg,self.req);self.assertEqual(r.choices[0].message.content,'backup');self.assertEqual([v['provider'] for v in a.records],['coco','coco2']);self.assertTrue(a.records[0]['streaming_requested']);self.assertFalse(a.records[0]['first_chunk_received']);self.assertTrue(a.records[1]['terminal_trusted']);self.assertEqual(a.snapshot()['logical_requests'],1)
    async def test_error_after_role_chunk_safe_fallback(self):
        g=self.gateway([chunk(),APIConnectionError(request=httpx.Request('POST','http://mock.invalid'))]);a=RuntimeAccounting();r=await a.request(g,self.cfg,self.req);self.assertEqual(response_status(r)['status'],'complete');self.assertEqual(len(a.records),2);self.assertEqual(len(self.back.requests),1)
    async def test_error_after_tool_fragment_discards_call(self):
        from scripts.streaming_fixtures import tool
        g=self.gateway([chunk(tools=[tool(0,'a','list_','{')]),OSError('closed')]);a=RuntimeAccounting();r=await a.request(g,self.cfg,self.req);self.assertIsNone(r.choices[0].message.tool_calls);self.assertEqual(len(self.back.requests),1)
    async def test_budget_blocks_fallback(self):
        g=self.gateway([APIConnectionError(request=httpx.Request('POST','http://mock.invalid'))]);g.before_fallback=lambda _:False;a=RuntimeAccounting()
        with self.assertRaises(FallbackBudgetExceeded):await a.request(g,self.cfg,self.req)
        self.assertEqual(len(a.records),1);self.assertEqual(self.back.requests,[])
    async def test_input_budget_before_dispatch(self):
        cfg=replace(self.cfg,context_token_budget={'mode':'estimate','input_limit':256});g=self.gateway([chunk('x',finish='stop')]);a=RuntimeAccounting()
        with self.assertRaises(TokenBudgetError):await a.request(g,cfg,{**self.req,'messages':[dict(role='user',content='x'*3000)]})
        self.assertEqual(a.records,[])
    async def test_partial_usage_not_zero(self):
        g=self.gateway([chunk('half'),OSError('closed')]);a=RuntimeAccounting();await a.request(g,self.cfg,self.req);self.assertIsNone(a.snapshot()['provider_reported_total_tokens']);self.assertEqual(a.snapshot()['missing_usage_requests'],2)
    async def test_primary_timeout_after_chunk_safe_fallback(self):
        g=self.gateway([]);g._configs=(replace(self.cfg,request_timeout_seconds=.04),self.backup)
        stream=Stream([chunk('half'),chunk('late')],delay=.03);g._clients[0]=Client([stream]);a=RuntimeAccounting()
        r=await a.request(g,self.cfg,self.req)
        self.assertEqual(r.choices[0].message.content,'backup');self.assertTrue(stream.closed);self.assertEqual(len(a.records),2)
    async def test_cancel_no_fallback(self):
        g=self.gateway([]);s=Stream([chunk('late')],delay=10);g._clients[0]=Client([s]);a=RuntimeAccounting();t=asyncio.create_task(a.request(g,self.cfg,self.req));await asyncio.sleep(.01);t.cancel()
        with self.assertRaises(asyncio.CancelledError):await t
        self.assertTrue(s.closed);self.assertEqual(self.back.requests,[])
    async def test_real_sdk_sse_usage_http_once(self):
        requests=[]
        async def handler(request):
            requests.append(json.loads(request.content));packets=[dict(id='x',object='chat.completion.chunk',created=1,model='mock',**chunk('真正协议\n',finish='stop')),dict(id='x',object='chat.completion.chunk',created=1,model='mock',choices=[],usage=dict(prompt_tokens=2,completion_tokens=3,total_tokens=5))]
            return httpx.Response(200,headers={'content-type':'text/event-stream'},text=''.join('data: '+json.dumps(p)+'\n\n' for p in packets)+'data: [DONE]\n\n')
        async with AsyncOpenAI(api_key='synthetic',base_url='http://mock.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as c:
            a=RuntimeAccounting();r=await a.request(c,self.cfg,self.req)
        self.assertEqual(response_status(r)['status'],'complete');self.assertEqual(len(requests),1);self.assertEqual(a.snapshot()['http_dispatch_attempts'],1);self.assertEqual(a.snapshot()['provider_reported_total_tokens'],5)
    async def test_unknown_unsupported_stream_no_retry(self):
        c=Client([TypeError('unsupported stream')]);a=RuntimeAccounting()
        with self.assertRaises(TypeError):await a.request(c,self.cfg,self.req)
        self.assertEqual(len(c.requests),1)
    async def test_usage_null_trailing_chunk(self):
        g=self.gateway([chunk('ok',finish='stop'),dict(choices=[],usage=None)]);a=RuntimeAccounting();await a.request(g,self.cfg,self.req);self.assertFalse(a.snapshot()['usage_complete'])

def check_streaming_failover():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FailoverStreamChecks))
    if not r.wasSuccessful():raise AssertionError('stream failover checks failed')
if __name__=='__main__':check_streaming_failover()
