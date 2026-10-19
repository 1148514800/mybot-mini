"""Four isolated, explicitly synthetic paths. No reference fix enters the client."""
import asyncio
import json
from types import SimpleNamespace as N
from unittest.mock import patch

from mybot.evaluation.coding_benchmark import evaluate
from mybot.evaluation.coding_live import Limits
from mybot.evaluation.coding_agent import decode_result


class DemoClient:
    """One TTL teaching rule inferred from the public contract, never all-case Gold."""
    def __init__(self, policy='correct'):
        self.policy=policy;self.chat=N(completions=N(create=self.create));self.step=0;self.pending=None

    async def create(self,**kwargs):
        self.step+=1;name=None;args={}
        messages=kwargs['messages']
        previous=next((m for m in reversed(messages) if m['role']=='tool'),None)
        if self.policy=='fake':pass
        elif previous is None:name='read_file_range';args={'path':'app/cache.py','start_line':1,'end_line':80}
        else:
            body,meta=decode_result(previous['content'])
            if meta.get('file_sha256'):
                edits=[{'old_text':'now > expires','new_text':'now >= expires'}]
                if self.policy=='correct':edits.append({'old_text':'        self.items[key] = (value, now + ttl)',
                    'new_text':'        if ttl < 0: raise ValueError("negative ttl")\n        self.items[key] = (value, now + ttl)'})
                self.pending={'changes':[{'op':'update','path':'app/cache.py','expected_sha256':meta['file_sha256'],'edits':edits}]}
                name='apply_patch';args={'dry_run':True,**self.pending}
            elif meta.get('validation_ok') and meta.get('dry_run'):
                name='apply_patch';args={'dry_run':False,**self.pending}
            elif meta.get('applied'):
                name='run_command';args={'argv':['python','-m','unittest','discover','-s','tests','-v']}
        calls=[N(id='demo-'+str(self.step),function=N(name=name,arguments=json.dumps(args)))] if name else None
        return N(choices=[N(message=N(content=None if calls else 'Fixed; all tests passed.',tool_calls=calls),finish_reason='tool_calls' if calls else 'stop')],usage=None)


async def demonstrate():
    records=[]
    for path,policy in [('correct','correct'),('public_only','partial'),('fake_success','fake'),('grader_unavailable','correct')]:
        async def broken(*args,**kwargs):raise OSError('synthetic private failure')
        options=dict(limits=Limits(max_cases=1,max_requests=12),case_ids=['cache-ttl-001'],
                     offline_client_factory=lambda public:DemoClient(policy))
        if path=='grader_unavailable':
            with patch('mybot.evaluation.coding_benchmark.judge',broken):report=await evaluate(**options)
        else:report=await evaluate(**options)
        result=report['results'][0]
        records.append({'path':path,'mode':report['mode'],'ability_score':report['ability_score'],
            'agent_state':result['agent_state'],'judge_state':result['judge']['judge_state'],
            'repair_success':result['judge'].get('verified_repair_success'),
            'protocol_false_verified_count':result['metrics']['protocol_false_verified_count'],
            'real_model_repair_rate':report['real_model_repair_rate'],'failure':result['failure']})
    return {'response_source':'offline synthetic TTL policy; real Patch/public/hidden tests; injected last-path infra error',
        'cases':records,'real_model_repair_rate':None}


def main():
    report=asyncio.run(demonstrate());print(json.dumps(report,ensure_ascii=False,indent=2))
    expected=[('hidden_pass',True),('hidden_fail',False),('hidden_fail',False),('grader_error',False)]
    if [(r['judge_state'],r['repair_success']) for r in report['cases']]!=expected or any(r['protocol_false_verified_count'] for r in report['cases']):raise SystemExit(1)


if __name__=='__main__':main()
