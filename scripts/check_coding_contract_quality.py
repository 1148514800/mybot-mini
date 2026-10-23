"""Fresh domains verify prompt delivery and native read flow, not model ability."""
import json
from mybot.agent import AgentLoop,ContextBuilder
from mybot.agent.context import SYSTEM_RULES
from mybot.agent.coding_controller import CodingTaskController,AutonomySettings
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from scripts.modernization_fixtures import Base,Client,response,call,run

CASES={
 'meter':('Compute signed meter deltas. Preserve negative values; zero follows the stated display contract.','src/meter.py','def delta(a,b): return a-b\n','numeric zero/sign/rounding'),
 'roster':('Return an empty list for no members; retain original order and leave input unchanged.','src/roster.py','def roster(items): return list(items)\n','empty collections'),
 'catalog':('Normalize search labels with Unicode normalization and preserve first display spelling.','src/catalog.py','def labels(items): return items\n','Unicode'),
 'capacity':('Capacity accepts exact integers; bool is invalid. Invalid capacity raises ValueError.','src/capacity.py','def capacity(value): return value\n','types'),
 'dispatch':('The public dispatch entry must call routing.choose; serialized output follows README.','src/dispatch.py','from .routing import choose\ndef dispatch(x): return choose(x)\n','real business entry'),
}

class ContractChecks(Base):
    async def exercise(self,name):
        contract,path,source,concept=CASES[name];(self.root/'src').mkdir(exist_ok=True)
        (self.root/'README.md').write_text(contract);(self.root/path).write_text(source)
        if name=='dispatch':(self.root/'src/routing.py').write_text('def choose(x): return x\n')
        cfg=GatewayConfig(workspace=self.root,coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'macos_readonly'},
            coding_autonomy={'enabled':True},session_persist=False,skills_enabled=False,mcp_enabled=False,max_react_steps=6)
        actions=[response(calls=[call('read-contract','read_file','{"path":"README.md"}')]),
                 response(calls=[call('read-entry','read_file',json.dumps({'path':path}))])]
        if name=='dispatch':actions.append(response(calls=[call('read-helper','read_file','{"path":"src/routing.py"}')]))
        client=Client(actions+[response('Contract read; no repair or tests performed.')])
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',command={'mode':'macos_readonly'})
        a=AgentLoop(client,cfg,tools,ContextBuilder(self.root));await a.handle_message('Investigate the contract in README; only read files.')
        self.assertIn(contract,str(client.requests[-1]['messages']));self.assertTrue(any(m['role']=='tool' and m['content']==source for m in client.requests[-1]['messages']))
        if name=='dispatch':self.assertIn('def choose(x): return x',str(client.requests[-1]['messages']))
        self.assertIn(concept,client.requests[0]['messages'][0]['content']);self.assertIn('disclose untested requirements',client.requests[0]['messages'][0]['content'])
        self.assertNotEqual(a.last_coding_report['state'],'verified');self.assertEqual(a.last_coding_report['committed_patches'],0)
        self.assertEqual((self.root/path).read_text(),source);self.assertEqual(len(client.requests),4 if name=='dispatch' else 3)
    async def test_numeric_domain(self):await self.exercise('meter')
    async def test_empty_collection_domain(self):await self.exercise('roster')
    async def test_unicode_domain(self):await self.exercise('catalog')
    async def test_exact_type_domain(self):await self.exercise('capacity')
    async def test_cross_module_domain(self):await self.exercise('dispatch')
    async def test_no_old_answer_or_blanket_test_requirement(self):
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',command={'mode':'macos_readonly'})
        text=CodingTaskController(AutonomySettings(enabled=True),tools).instruction()
        for secret_answer in ("Decimal('-2')",'zero-negative','parcel_totals','EXIF','待确认日期'):self.assertNotIn(secret_answer,text)
        self.assertIn('Choose only relevant',text);self.assertNotIn('all boundary cases must',text)
        self.assertIn('先简洁覆盖用户要求的全部部分',SYSTEM_RULES)


def check_coding_contract_quality():run(ContractChecks)
if __name__=='__main__':check_coding_contract_quality()
