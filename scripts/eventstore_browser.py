"""Explicit disposable browser acceptance server; persistent synthetic data only."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import uvicorn
from mybot.web.server import create_app
from scripts.eventstore_fixtures import configuration,SyntheticClient
from scripts.check_session import response,call


class BrowserClient(SyntheticClient):
    def __init__(self,root,crash=False):super().__init__();self.root=root;self.crash=crash
    async def create(self,**kwargs):
        with (self.root/'synthetic-requests').open('a') as stream:stream.write('synthetic\n')
        text=kwargs['messages'][-1].get('content','')
        if self.crash and text=='中断演练':
            marker=self.root/'child-pid'
            code='import os,pathlib,time;pathlib.Path('+repr(str(marker))+').write_text(str(os.getpid()));time.sleep(90)'
            return response(calls=[call('synthetic-command','run_command',json.dumps({'argv':['python','-c',code]}))])
        return await super().create(**kwargs)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state-dir',type=Path,required=True);parser.add_argument('--port',type=int,default=8887);parser.add_argument('--crash',action='store_true');args=parser.parse_args()
    root=args.state_dir.resolve();root.mkdir(mode=0o700,parents=True,exist_ok=True)
    options={} if not args.crash else dict(coding_enabled=True,coding_patch_mode='write',coding_preview_receipt=True,coding_command={'mode':'host_confirm'},context_max_chars=20000)
    cfg=configuration(root,**options)
    app=create_app(cfg,port=args.port,client_factory=lambda c:BrowserClient(root,args.crash),approval_timeout=180)
    uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,timeout_graceful_shutdown=2)

if __name__=='__main__':main()
