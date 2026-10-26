"""Disposable async stream packets, never a real provider."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace as N

def chunk(text=None,finish=None,tools=None,usage=None):
    delta={}
    if text is not None:delta['content']=text
    if tools is not None:delta['tool_calls']=tools
    return dict(choices=[dict(index=0,delta=delta,finish_reason=finish)],usage=usage)

def tool(index=0,id=None,name=None,args=None):
    return dict(index=index,id=id,type='function',function=dict(name=name,arguments=args))

class Stream:
    def __init__(self,packets,delay=0,error=None):self.packets=packets;self.delay=delay;self.error=error;self.closed=False
    async def __aiter__(self):
        for p in self.packets:
            if self.delay:await asyncio.sleep(self.delay)
            if isinstance(p,BaseException):raise p
            yield p
        if self.error:raise self.error
    async def close(self):self.closed=True

class Client:
    def __init__(self,streams):self.streams=list(streams);self.requests=[];self.closed=False;self.chat=N(completions=N(create=self.create))
    async def create(self,**request):
        self.requests.append(deepcopy(request));value=self.streams.pop(0)
        if isinstance(value,BaseException):raise value
        return value
    async def close(self):self.closed=True
