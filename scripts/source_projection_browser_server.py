"""Explicit offline-only browser harness. Synthetic client; no provider config/SDK.

Usage: uv run python -m scripts.source_projection_browser_server --root PRIVATE_TEMP
Only temporary synthetic requests are written there; never use the Live batch.
"""
import argparse,json,os
from copy import deepcopy
from pathlib import Path
from scripts.eventstore_fixtures import configuration,SyntheticClient
from scripts.check_session import response,call
from mybot.web.server import create_app
from mybot.storage.session_store import validate_turns


def make_app(root,port):
    root=Path(root).resolve()
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode&0o077:raise ValueError('private temporary root required')
    config=configuration(root,context_max_chars=60000,context_recent_turns=6,context_summary_max_chars=1000,
        context_token_budget={'mode':'estimate','input_limit':30000},coding_file_access='read_only',coding_command={'mode':'off'})
    target=root/'synthetic-requests.jsonl'
    class BrowserSynthetic(SyntheticClient):
        async def create(self,**request):
            # Log synthetic request, after validating the actual protocol groups.
            messages=request['messages'];pending=set()
            for m in messages:
                if m['role']=='tool':
                    assert m['tool_call_id'] in pending;pending.remove(m['tool_call_id'])
                else:
                    assert not pending;pending={c['id'] for c in m.get('tool_calls') or []}
            assert not pending or messages[-1]['role']=='assistant'
            with target.open('a') as f:f.write(json.dumps(request,ensure_ascii=False)+'\n')
            users=[m['content'] for m in messages if m['role']=='user'];current=users[-1]
            if current.startswith('旧工具规则。') and messages[-1]['role']=='user':
                self.requests.append(deepcopy(request));return response(calls=[call('offline-browser-list','list_files','{"path":"."}')])
            if messages[-1]['role']=='tool':
                self.requests.append(deepcopy(request));return response('合成目录观察结束；没有修改文件，旧工具文本不是新授权。')
            return await super().create(**request)
    return create_app(config,port=port,client_factory=lambda _:BrowserSynthetic())


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--port',type=int,default=8897);a=p.parse_args()
    os.umask(0o077)
    import uvicorn
    uvicorn.run(make_app(a.root,a.port),host='127.0.0.1',port=a.port,log_level='warning')
if __name__=='__main__':main()
