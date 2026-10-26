"""Only a private synthetic SDK MockTransport server; never real provider URLs."""
import argparse,asyncio,json,os
from pathlib import Path
import httpx
from openai import AsyncOpenAI
from scripts.eventstore_fixtures import configuration
from scripts.streaming_fixtures import chunk,tool
from mybot.web.server import create_app


def make_app(root,port):
    root=Path(root).resolve()
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode&0o077:raise ValueError('private temp required')
    cfg=configuration(root,web_streaming=True,web_steer=True,context_max_chars=60000,context_recent_turns=6,
        context_token_budget={'mode':'estimate','input_limit':30000},coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'host_confirm'})
    (cfg.workspace/'public.txt').write_text('synthetic protected original\n')
    class Bytes(httpx.AsyncByteStream):
        def __init__(self,packets,delay,broken=False):self.packets,self.delay,self.broken=packets,delay,broken
        async def __aiter__(self):
            for p in self.packets:
                await asyncio.sleep(self.delay)
                yield ('data: '+json.dumps(dict(id='synthetic',object='chat.completion.chunk',created=1,model='synthetic',**p))+'\n\n').encode()
            if self.broken:raise OSError('synthetic connection interruption')
            yield b'data: [DONE]\n\n'
        async def aclose(self):
            with (root/'stream-closes.log').open('a') as f:f.write('closed\n')
    async def handler(request):
        body=json.loads(request.content);assert body['stream'] is True;assert body['stream_options']=={'include_usage':True}
        with (root/'sdk-requests.jsonl').open('a') as f:f.write(json.dumps(body,ensure_ascii=False)+'\n')
        users=[m['content'] for m in body['messages'] if m['role']=='user'];original=next((t for t in users if t.startswith('场景')),'');steered=any('用户在本Turn补充' in t for t in users)
        broken=False;delay=.18
        if original.startswith('场景B') and not steered:
            packets=[chunk('正在准备尚未执行的工具。\n'),chunk(tools=[tool(0,'held-patch','apply_','{"dry_run":')]),chunk(tools=[tool(0,name='patch',args='true,"changes":[]}')],finish='tool_calls')];delay=.7
        elif original.startswith('场景D'):
            packets=[chunk('这是一段未完成的中文回复。\n'),chunk(tools=[tool(0,'partial-tool','apply_patch','{"dry_run":')])];broken=True
        elif original.startswith('场景F'):
            packets=[chunk(tools=[tool(0,'approval-test','run_command','{"argv":["python3","-c","print(1)"]}')],finish='tool_calls')]
        elif original.startswith('场景E'):
            packets=[chunk(f'重连第{i:02}行。\n') for i in range(30)]+[chunk(finish='stop')];delay=.22
        elif original.startswith('场景H'):
            packets=[chunk(f'可取消第{i}行。\n') for i in range(30)]+[chunk(finish='stop')];delay=.3
        elif steered:packets=[chunk('下一模型步骤已收到用户补充。\n',finish='stop')]
        else:packets=[chunk(t) for t in ['早期中文已经出现。\n','这是 **真正的增量**。\n','```python\n','print("合成")\n','```\n','<script>window.syntheticXss=true</script>\n','结束行。\n']]+[chunk(finish='stop')];delay=.3
        if not broken:packets.append(dict(choices=[],usage=dict(prompt_tokens=10,completion_tokens=20,total_tokens=30)))
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes(packets,delay,broken))
    def factory(config):return AsyncOpenAI(api_key='synthetic-no-real-provider',base_url='http://synthetic.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return create_app(cfg,port=port,client_factory=factory)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,default=8899);a=p.parse_args();os.umask(0o077)
    import uvicorn
    uvicorn.run(make_app(a.root,a.port),host='127.0.0.1',port=a.port,log_level='warning')
if __name__=='__main__':main()
