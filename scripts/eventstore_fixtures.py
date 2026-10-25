"""Disposable event store/runtime fixtures; never instantiate a model SDK client."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace as N
from mybot.config import GatewayConfig
from mybot.agent.pinned_context import PIN_LABEL
from scripts.check_session import response


def configuration(root,**changes):
    values=dict(workspace=root/'workspace',session_backend='event_sqlite',session_event_path=root/'private/events.sqlite3',
        session_persist=False,api_key=None,provider='offline',model='synthetic',skills_enabled=False,mcp_enabled=False,
        context_enabled=True,context_max_chars=7000,context_recent_turns=1,context_summary_max_chars=300,
        max_react_steps=10)
    (root/'workspace').mkdir(exist_ok=True)
    return GatewayConfig(**(values|changes))


class SyntheticClient:
    def __init__(self):self.requests=[];self.closed=False;self.chat=N(completions=N(create=self.create))
    async def create(self,**kwargs):
        self.requests.append(deepcopy(kwargs))
        pins=[]
        for message in kwargs['messages']:
            if (message.get('content') or '').startswith(PIN_LABEL):
                assert message['role']=='user'
                pins=json.loads(message['content'][len(PIN_LABEL):])
        return response('合成回复；当前请求固定事项：'+json.dumps([p['content'] for p in pins],ensure_ascii=False)+'；本会话安全历史可查看。')
    async def close(self):self.closed=True
