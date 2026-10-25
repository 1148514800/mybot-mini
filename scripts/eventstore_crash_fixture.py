"""Kill only this disposable worker at a named durability boundary; no model SDK."""
import argparse
import asyncio
import os
from pathlib import Path
import sys
import json
from mybot.storage.history import SessionHistory,open_store
from mybot.storage.event_schema import Event,identifier
from mybot.tools import build_default_tool_registry
from scripts.eventstore_fixtures import configuration
from scripts.authority_contract_fixtures import approve


async def run(root,stage):
    config=configuration(root)
    store=open_store(config,'web');h=SessionHistory(store)
    (root/'session-id').write_text(h.sid)
    if stage=='created':os._exit(17)
    if stage=='user_only':
        store.append(Event.create(h.sid,'user.message',dict(turn_id=identifier(),content='actual user input',truncated=False),source='user',privacy_class='chat'));os._exit(17)
    h.start('synthetic interrupted task')
    if stage=='model':h.event('model.started',dict(turn_id=h.turn_id,purpose='agent'));os._exit(17)
    tools=build_default_tool_registry(config.workspace,coding_enabled=True,patch_mode='write',preview_receipt=True,
        command={'mode':'host_confirm'},command_approval_provider=approve)
    tools.execution_observer=h
    if stage in ('read_pending','effect_pending'):
        h.begin('read_file',{},tools.get_tool('read_file'),'read_only' if stage=='read_pending' else 'external_side_effect');os._exit(17)
    patch=tools.get_tool('apply_patch');patch.begin_receipt_scope()
    preview=await tools.execute('apply_patch',{'changes':[{'op':'add','path':'new.py','content':'VALUE = 7\n'}],'dry_run':True})
    assert preview.success
    if stage=='preview':os._exit(17)
    if stage=='commit_gap':
        original=h.complete
        def crash(token,result):os._exit(17)
        h.complete=crash
    commit=await tools.execute('apply_patch',preview.metadata['commit_arguments']);assert commit.success
    if stage in ('commit','commit_gap'):os._exit(17)
    if stage=='command':
        marker=root/'child-pid'
        code='import os,pathlib,time;pathlib.Path('+repr(str(marker))+').write_text(str(os.getpid()));time.sleep(30)'
        task=asyncio.create_task(tools.execute('run_command',{'argv':['python','-c',code]}))
        for _ in range(500):
            if marker.exists():os._exit(17)
            if task.done():raise AssertionError((await task).to_text())
            await asyncio.sleep(.01)
        raise AssertionError('command did not start')
    if stage=='test_finished':
        (config.workspace/'test_x.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_x(self):self.assertEqual(7,7)\n')
        test=await tools.execute('run_command',{'argv':['python','-m','unittest','test_x']});assert test.success
        os._exit(17)
    raise ValueError('stage')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('stage');args=parser.parse_args()
    asyncio.run(run(args.root,args.stage))
