"""Offline decision acceptance server: synthetic SDK only, private temp root."""
import argparse,json,os
from pathlib import Path
from copy import deepcopy
from scripts.eventstore_fixtures import configuration,SyntheticClient
from scripts.check_session import response
from mybot.web.server import create_app


def make_app(root,port):
    root=Path(root).resolve()
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode&0o077:raise ValueError('private temporary root required')
    cfg=configuration(root,context_max_chars=60000,context_recent_turns=6,
        context_token_budget={'mode':'estimate','input_limit':30000},coding_command={'mode':'off'})
    class DecisionSynthetic(SyntheticClient):
        async def create(self,**request):
            # Only public synthetic data; this file stays outside Git.
            self.requests.append(deepcopy(request))
            with (root/'synthetic-requests.jsonl').open('a') as f:f.write(json.dumps(request,ensure_ascii=False)+'\n')
            return response('原始笔记永久保留是已确定要求。\n（合成错误回答：用于证明普通模型回答不会变成宿主可信事项。）')
    return create_app(cfg,port=port,client_factory=lambda _:DecisionSynthetic())


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,default=8898);a=p.parse_args();os.umask(0o077)
    import uvicorn
    uvicorn.run(make_app(a.root,a.port),host='127.0.0.1',port=a.port,log_level='warning')
if __name__=='__main__':main()
