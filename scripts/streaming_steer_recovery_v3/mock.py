"""New independent Mock batch, genuine AsyncOpenAI SDK MockTransport only."""
import argparse,json,os
from dataclasses import replace
from pathlib import Path
from mybot.workspace import init_workspace
from scripts.streaming_steer_real_uat_v2.mock import build_mock
from scripts.uat_operator.ports import serve
from .plan import config_for,plan_hash,BARRIER
from .budget import Ledger,private_directory
from .server import owned_app

def make_mock(root,port,case,mode='normal',*,barriers=BARRIER,delay=.14):
 root=Path(root).resolve();private_directory(root);private_directory(root/'private')
 cfg=config_for(root,dict(model='deepseek-v4.1-flash',base_url='http://mock.invalid/v1',api_key='synthetic-only'))
 if not cfg.workspace.exists():cfg.workspace.mkdir(mode=0o700);init_workspace(cfg.workspace)
 ledger=Ledger(root/'private/requests.sqlite',plan_hash());counter=[];backup=replace(cfg,provider='coco2',model='glm-5.3-flash')
 # Reuse provider transport frames, never the old case's app/ledger/state.
 builder=build_mock('T02' if case=='N01' else 'T03',mode,counter,delay)
 app=owned_app(case,root,cfg,backup,ledger,builder,lambda allow_halt:None,port,barriers=barriers);app.mock_requests=counter;return app

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--case',choices=['N01','N02'],required=True);p.add_argument('--status-file',type=Path,required=True);a=p.parse_args();os.umask(0o077)
 serve(lambda port:make_mock(a.root,port,a.case),a.port,a.status_file)
if __name__=='__main__':main()
