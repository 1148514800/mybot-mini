"""Disposable native Web fixture for macOS socket/SSE lifecycle checks. No SDK."""
import argparse,asyncio,json
from pathlib import Path
from contextlib import asynccontextmanager
from mybot.web.server import create_app
from mybot.workspace_lease import WorkspaceLease
from mybot.workspace import init_workspace
from scripts.streaming_steer_recovery_v3.plan import config_for
from .ports import serve,write_status

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--status-file',type=Path,required=True);p.add_argument('--ready-delay',type=float,default=0);a=p.parse_args()
 def build(port):
  root=a.root;root.mkdir(mode=0o700,exist_ok=True);(root/'workspace').mkdir(mode=0o700,exist_ok=True);init_workspace(root/'workspace')
  cfg=config_for(root,dict(api_key=None,model='synthetic-only',base_url='http://mock.invalid/v1'))
  app=create_app(cfg,port=port,client_factory=lambda _:None);native=app.app.router.lifespan_context
  @asynccontextmanager
  async def owned(application):
   lease=WorkspaceLease(cfg.workspace).acquire()
   try:
    await asyncio.sleep(a.ready_delay)
    async with native(application):yield
   finally:
    lease.release();write_status(root/'cleanup.json',dict(lease_released=True,runtime_closed=app.runtime.closed,real_requests=0))
  app.app.router.lifespan_context=owned;return app
 serve(build,a.port,a.status_file)
if __name__=='__main__':main()
