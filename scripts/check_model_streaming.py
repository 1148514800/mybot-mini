import asyncio,unittest,json
from mybot.agent.streaming import consume,SafePreview,StreamCleanupError
from mybot.runtime_accounting import response_status,usage_values
from scripts.streaming_fixtures import chunk,tool,Stream

class StreamingChecks(unittest.IsolatedAsyncioTestCase):
    async def assemble(self,packets,**kw):
        stream=Stream(packets);result=await consume(stream,**kw);self.assertTrue(stream.closed);return result
    async def test_chinese(self):
        r=await self.assemble([chunk('你'),chunk('好\n'),chunk(finish='stop')]);self.assertEqual(r.choices[0].message.content,'你好\n');self.assertEqual(response_status(r)['status'],'complete')
    async def test_markdown(self):
        r=await self.assemble([chunk('```py\n'),chunk('print(1)\n'),chunk('```\n',finish='stop')]);self.assertIn('```py\nprint(1)\n```',r.choices[0].message.content)
    async def test_usage_empty_choices(self):
        r=await self.assemble([chunk('ok',finish='stop'),dict(choices=[],usage=dict(prompt_tokens=1,completion_tokens=2,total_tokens=3))]);self.assertEqual(usage_values(r.usage)['total_tokens'],3)
    async def test_missing_usage_unknown(self):self.assertIsNone(usage_values((await self.assemble([chunk('ok',finish='stop')])).usage)['total_tokens'])
    async def test_length(self):self.assertEqual(response_status(await self.assemble([chunk('partial',finish='length')]))['status'],'output_truncated')
    async def test_filter(self):self.assertEqual(response_status(await self.assemble([chunk('filtered',finish='content_filter')]))['status'],'content_filtered')
    async def test_missing_finish(self):self.assertEqual(response_status(await self.assemble([chunk('partial')]))['status'],'response_unconfirmed')
    async def test_empty_stop(self):self.assertEqual(response_status(await self.assemble([chunk('',finish='stop')]))['status'],'empty_response')
    async def test_unknown_finish(self):self.assertEqual(response_status(await self.assemble([chunk('ok',finish='strange')]))['status'],'response_unconfirmed')
    async def test_split_tools(self):
        r=await self.assemble([chunk(tools=[tool(id='a',name='list_',args='{')]),chunk(tools=[tool(name='files',args='"path":"."}')],finish='tool_calls')]);self.assertEqual(r.choices[0].message.tool_calls[0].function.arguments,'{"path":"."}')
    async def test_parallel_tool_indices(self):
        r=await self.assemble([chunk(tools=[tool(1,'b','list_files','{"path":'),tool(0,'a','list_files','{')]),chunk(tools=[tool(0,args='"path":"a"}'),tool(1,args='"b"}')],finish='tool_calls')]);self.assertEqual([t.id for t in r.choices[0].message.tool_calls],['a','b'])
    async def test_partial_json_no_calls(self):
        for args in ('{','{"x":NaN}','{"x":1,"x":2}'):
            r=await self.assemble([chunk(tools=[tool(id='a',name='list_files',args=args)],finish='tool_calls')]);self.assertIsNone(r.choices[0].message.tool_calls);self.assertEqual(response_status(r)['status'],'provider_error')
    async def test_missing_finish_tools_no_legacy_promotion(self):
        r=await self.assemble([chunk(tools=[tool(id='a',name='list_files',args='{}')])]);self.assertEqual(response_status(r)['status'],'response_unconfirmed');self.assertIsNone(r.choices[0].message.tool_calls)
    async def test_stop_with_tools_invalid(self):self.assertEqual(response_status(await self.assemble([chunk(tools=[tool(id='a',name='list_files',args='{}')],finish='stop')]))['status'],'provider_error')
    async def test_tool_gap(self):self.assertIsNone((await self.assemble([chunk(tools=[tool(2,'a','list_files','{}')],finish='tool_calls')])).choices[0].message.tool_calls)
    async def test_duplicate_call_ids(self):self.assertIsNone((await self.assemble([chunk(tools=[tool(0,'a','list_files','{}'),tool(1,'a','list_files','{}')],finish='tool_calls')])).choices[0].message.tool_calls)
    async def test_broken_stream_no_usage(self):
        r=await self.assemble([chunk('half\n',usage={'total_tokens':100}),OSError('private error')]);self.assertEqual(response_status(r)['status'],'provider_error');self.assertIsNone(r.usage)
    async def test_cancel_closes(self):
        s=Stream([chunk('x')],delay=10);t=asyncio.create_task(consume(s));await asyncio.sleep(.01);t.cancel()
        with self.assertRaises(asyncio.CancelledError):await t
        self.assertTrue(s.closed)
    async def test_close_failure_uncertain(self):
        class Bad(Stream):
            async def close(self):raise OSError('private')
        with self.assertRaises(StreamCleanupError):await consume(Bad([chunk('ok',finish='stop')]))
    async def test_concurrent_isolation(self):
        a,b=await asyncio.gather(self.assemble([chunk('A\n',finish='stop')]),self.assemble([chunk('B\n',finish='stop')]));self.assertEqual(a.choices[0].message.content,'A\n');self.assertEqual(b.choices[0].message.content,'B\n')
    async def test_output_limit(self):self.assertEqual(response_status(await self.assemble([chunk('x'*32769)]))['status'],'output_truncated')
    async def test_tool_limit(self):self.assertEqual(response_status(await self.assemble([chunk(tools=[tool(16,'a','bad','{}')])]))['status'],'provider_error')
    async def test_no_tool_arguments_in_events(self):
        seen=[];await self.assemble([chunk(tools=[tool(0,'a','list_files','{"path":"private-argument"}')],finish='tool_calls')],notify=seen.append);self.assertNotIn('private-argument',str(seen))
    async def test_split_known_secret(self):
        seen=[];key='example-private-credential';await self.assemble([chunk('example-'),chunk('private-'),chunk('credential\n'),chunk('安全\n',finish='stop')],notify=seen.append,secrets=(key,));self.assertNotIn(key,str(seen));self.assertIn('安全',str(seen))
    async def test_split_receipt_nonce(self):
        seen=[];await self.assemble([chunk('receipt='+'a'*20),chunk('a'*20),chunk('a'*24+'\nnonce=private-value\n',finish='stop')],notify=seen.append);self.assertNotIn('a'*20,str(seen));self.assertNotIn('private-value',str(seen))
    async def test_long_line_suppressed_bounded(self):
        p=SafePreview();out=''.join(p.feed('x'*1000) for _ in range(20));self.assertEqual(out,'');self.assertLessEqual(len(p.pending),4096);self.assertIn('隐藏',p.feed('\n'))
    async def test_multiline_secret_preview_disabled(self):self.assertEqual(SafePreview(('hello\nworld',)).feed('hello\n'), '')
    async def test_nontext_structure_invalid(self):self.assertEqual(response_status(await self.assemble([chunk({'bad':1})]))['status'],'provider_error')
    async def test_chunks_after_finish_invalid(self):self.assertEqual(response_status(await self.assemble([chunk('x',finish='stop'),chunk('y')]))['status'],'provider_error')
    async def test_oversized_tool_argument_refused(self):
        r=await self.assemble([chunk(tools=[tool(0,'a','list_files','x'*70000)],finish='tool_calls')]);self.assertIsNone(r.choices[0].message.tool_calls);self.assertEqual(response_status(r)['status'],'provider_error')
    async def test_unexpected_role_refused(self):
        p=chunk('x',finish='stop');p['choices'][0]['delta']['role']='user';self.assertEqual(response_status(await self.assemble([p]))['status'],'provider_error')
    async def test_close_timeout_is_uncertain(self):
        class Hanging(Stream):
            async def close(self):await asyncio.sleep(10)
        with self.assertRaises(StreamCleanupError):await consume(Hanging([chunk('done',finish='stop')]))
    async def test_preview_before_finish(self):
        seen=[];s=Stream([chunk('早期\n'),chunk('终轮\n',finish='stop')],delay=.06);t=asyncio.create_task(consume(s,notify=seen.append));await asyncio.sleep(.09);self.assertFalse(t.done());self.assertTrue(any(e['type']=='model_text_delta' for e in seen));await t

def check_model_streaming():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StreamingChecks))
    if not r.wasSuccessful():raise AssertionError('streaming checks failed')
if __name__=='__main__':check_model_streaming()
