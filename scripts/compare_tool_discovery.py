"""Fixed-script offline comparison with real MCP tools; counts are not model ability or cost."""
import asyncio
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as N

from mybot.agent import AgentLoop, ContextBuilder
from mybot.config import GatewayConfig
from mybot.mcp_client.manager import MCPClientManager
from mybot.tools import build_default_tool_registry
from scripts.mcp_catalog_demo_server import DEFINITIONS

CASES = {
    'project_tasks': [('project tasks','list_project_tasks',{'project':'mini','status':'pending'},'TASK-1')],
    'document_query': [('documents architecture','search_documents',{'query':'architecture'},'DOC-1')],
    'two_categories': [('project tasks','list_project_tasks',{'project':'mini'},'TASK-2'),
                       ('documents architecture','search_documents',{'query':'architecture'},'DOC-1')],
}


def demo_server():
    return {'command':sys.executable,'args':['-m','scripts.mcp_catalog_demo_server'],
            'allowed_tools':list(DEFINITIONS),'tool_policies':{name:'allow' for name in DEFINITIONS},'timeout_seconds':5}


class FixedDiscoveryClient:
    def __init__(self, progressive, steps):
        self.actions=[]
        for query,remote,arguments,expected in steps:
            name='mcp__catalog__'+remote
            if progressive:
                self.actions.extend([('search_mcp_tools',{'query':query},name),
                                     ('activate_mcp_tools',{'names':[name]},None)])
            self.actions.append((name,arguments,expected))
        self.index=0
        self.schemas=[]
        self.initial_visible_tools=0
        self.search_calls=self.activate_calls=0
        self.last=None
        self.chat=N(completions=N(create=self.create))

    async def create(self, **kwargs):
        definitions=kwargs['tools'] or []
        visible={item['function']['name'] for item in definitions}
        self.schemas.append(len(json.dumps(definitions,ensure_ascii=False)))
        if len(self.schemas)==1:self.initial_visible_tools=len(definitions)
        if self.last is not None:
            name,_,expected=self.last
            result=next(m['content'] for m in reversed(kwargs['messages']) if m['role']=='tool')
            if name=='search_mcp_tools':
                if expected not in {entry['name'] for entry in json.loads(result)['matches']}:
                    raise AssertionError('Fixed expected target absent from search results')
            elif expected is not None and expected not in result:
                raise AssertionError('Actual synthetic tool result did not satisfy case')
        if self.index == len(self.actions):
            return N(choices=[N(message=N(content='Synthetic task complete.',tool_calls=None))],usage=None)
        name,arguments,expected=self.actions[self.index]
        if name not in visible:raise AssertionError('Fixed script attempted an invisible tool')
        self.index+=1;self.last=(name,arguments,expected)
        self.search_calls+=name=='search_mcp_tools';self.activate_calls+=name=='activate_mcp_tools'
        call=N(id=f'call-{self.index}',function=N(name=name,arguments=json.dumps(arguments)))
        return N(choices=[N(message=N(content=None,tool_calls=[call]))],usage=None)


async def compare_case(case_id, mode):
    progressive=mode=='progressive'
    steps=CASES[case_id]
    with tempfile.TemporaryDirectory(prefix='mybot-discovery-compare-') as folder:
        workspace=Path(folder)/'workspace';workspace.mkdir()
        config=GatewayConfig(workspace=workspace,session_persist=False,skills_enabled=False,debug=False,
            context_enabled=True,context_max_chars=160000,max_react_steps=16,
            mcp_enabled=True,mcp_servers={'catalog':demo_server()},mcp_discovery={'enabled':progressive})
        tools=build_default_tool_registry(workspace)
        client=FixedDiscoveryClient(progressive,steps)
        async with MCPClientManager(config,tools) as manager:
            agent=AgentLoop(client,config,tools,ContextBuilder(workspace))
            with contextlib.redirect_stdout(io.StringIO()):
                reply=await agent.handle_message('Complete the fixed synthetic '+case_id+' task.')
            actual=sum(event['executed'] for event in manager.audit)
            success=(reply=='Synthetic task complete.' and actual==len(steps)
                     and all(event['success'] for event in manager.audit))
        sizes=client.schemas
        return {'case_id':case_id,'mode':mode,'total_catalog_tools':len(DEFINITIONS),
            'initial_visible_tools':client.initial_visible_tools,'initial_schema_chars':sizes[0],
            'mean_schema_chars_per_request':round(sum(sizes)/len(sizes),2),
            'cumulative_schema_chars':sum(sizes),'llm_requests':len(sizes),'search_calls':client.search_calls,
            'activate_calls':client.activate_calls,'actual_tool_calls':actual,'task_success':success}


async def compare():
    return {'mode':'offline','response_source':'fixed_script_with_real_stdio_mcp',
            'ability_score':False,'actual_tokens':None,'actual_cost':None,
            'schema_char_measurement':'len(json.dumps(actual_tools_array, ensure_ascii=False))',
            'results':[await compare_case(case_id,mode) for case_id in CASES for mode in ('eager','progressive')]}


def main():print(json.dumps(asyncio.run(compare()),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
