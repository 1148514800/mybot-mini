"""Disposable OFFLINE/SYNTHETIC browser demo. No SDK, credentials or network model."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as N
import uvicorn
from mybot.config import GatewayConfig
from mybot.web.server import create_app
from mybot.agent.context_compactor import FIELDS,PROMPT
from scripts.check_session import response

HISTORY=[[dict(role='user',content='GOAL: 设计设备巡检助手\nCONSTRAINT: 不外发记录\nDECISION: 使用优先级展示\nUNKNOWN: 通知渠道尚未决定\nPENDING: 部署尚未开始\n'+'synthetic-history '*700),
          dict(role='assistant',content='OFFLINE/SYNTHETIC 合成历史；没有实施或测试。')]]

class DemoClient:
    def __init__(self):self.chat=N(completions=N(create=self.create))
    async def create(self,**request):
        if request['messages'][0]['content']==PROMPT:
            d={k:[] for k in FIELDS}
            for k,text in [('current_goal','GOAL: 设计设备巡检助手'),('user_constraints','CONSTRAINT: 不外发记录'),
                           ('decisions','DECISION: 使用优先级展示'),('uncertainty','UNKNOWN: 通知渠道尚未决定'),('pending_work','PENDING: 部署尚未开始')]:
                d[k]=[dict(turn=1,message=0,quote=text)]
            d['important_artifacts']=[dict(turn=1,message=0,quote='not in the source')]
            r=response(json.dumps(d,ensure_ascii=False))
        else:
            user=request['messages'][-1]['content']
            r=response('OFFLINE/SYNTHETIC：这是保留的部分回答；尚未实施或运行测试。' if '截断' in user else
                       'OFFLINE/SYNTHETIC：完整合成回复。有效历史包含巡检目标、不外发约束、优先级决定、通知渠道未知及尚未部署。没有执行工具或写文件。')
            if '截断' in user:r.choices[0].finish_reason='length'
        r.usage=N(prompt_tokens=7,completion_tokens=3,total_tokens=10)
        return r
    async def close(self):pass


def make_demo(root,port=8879):
    cfg=GatewayConfig(workspace=root,provider='offline-synthetic',model='quality-hardening-demo',api_key='synthetic-only-key',
        mcp_enabled=False,skills_enabled=False,session_persist=False,context_enabled=True,context_recent_turns=0,
        context_summary_max_chars=6000,context_token_budget={'mode':'estimate','input_limit':8000},
        context_compaction={'mode':'semantic','allow_extra_requests':True,'input_tokens':19000})
    app=create_app(cfg,port=port,client_factory=lambda c:DemoClient())
    original=app.runtime.new
    def new():
        c=original();c.session.restore(HISTORY);return c
    app.runtime.new=new
    return app

if __name__=='__main__':
    with TemporaryDirectory(prefix='mybot-quality-OFFLINE-SYNTHETIC-') as folder:
        uvicorn.run(make_demo(Path(folder).resolve()),host='127.0.0.1',port=8879,access_log=False,log_level='warning')
