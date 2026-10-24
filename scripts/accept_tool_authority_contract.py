"""Three disposable acceptance tasks, real tools and synthetic model responses only."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from scripts.authority_contract_fixtures import prepare,agent,PROMPTS


def git(root, *args):
    return subprocess.check_output(['/usr/bin/git','-c','core.hooksPath=/dev/null',
        '-c','commit.gpgsign=false', '-c','user.name=Synthetic', '-c','user.email=synthetic@example.invalid',*args],
        cwd=root,env={**os.environ,'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1'},stderr=subprocess.PIPE).decode()


def fingerprint(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


async def scenario(name):
    with tempfile.TemporaryDirectory(prefix='mybot-authority-accept-') as folder:
        root=Path(folder).resolve();prepare(root,name)
        git(root,'init','-q');git(root,'add','--all');git(root,'commit','-qm','synthetic fixture')
        before=fingerprint(root);status=git(root,'status','--porcelain')
        preview_unchanged=[];events=[]
        def observe(event):
            if event['type']=='tool_finished':
                events.append({'tool':event['tool'],'success':event['success'],
                               'authority_denied':event['metadata'].get('authority_denied',False),
                               'receipt_commit_success':event['metadata'].get('receipt_commit_success',False)})
                if event['tool']=='apply_patch' and event['metadata'].get('dry_run'):
                    preview_unchanged.append(hashlib.sha256((root/'core.py').read_bytes()).hexdigest()==before['core.py'])
        a,c=agent(root,name,callback=observe);reply=await a.handle_message(PROMPTS[name])
        result={'scenario':name,'synthetic_requests':len(c.requests),'real_api_requests':0,
                'controller':None,'contract':a.last_task_contract,'tool_results':events}
        if name=='C':
            assert fingerprint(root)==before and git(root,'status','--porcelain')==status
            assert len(c.requests)==1 and '权限拒绝' in reply
            result.update(result='PASS',files_unchanged=True,git_worktree_unchanged=True,denied_without_repair_request=True)
        else:
            report=a.last_coding_report
            result['controller']={key:report[key] for key in ('state','current_revision','committed_patches','test_runs','tests_passed_after_last_patch')}
            assert report['state']=='verified' and report['current_revision']==1 and all(preview_unchanged)
            assert any(e['receipt_commit_success'] for e in events)
            assert a.last_task_contract['task_correctness']=='unknown'
            result.update(result='PASS',preview_did_not_write=True,receipt_committed=True)
            if name=='B':
                import sys
                check=subprocess.run([sys.executable,'-B','-c','from service import handle; assert handle(None)==[]'],cwd=root,capture_output=True)
                assert check.returncode!=0 and a.last_task_contract['requirements'][1]['status']=='identified'
                result.update(independent_uncovered_requirement='FAIL',requirement_coverage='unknown',
                              independent_check_not_agent_evidence=True)
        return result


async def accept():
    return {'status':'SYNTHETIC_PASS','real_api_requests':0,'cases':[await scenario(n) for n in ('A','B','C')],
            'quality_claim':'Mechanism validation only; real-model task quality NOT_VERIFIED'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=asyncio.run(accept());args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Synthetic acceptance PASS: A/B/C, real API requests=0')

if __name__=='__main__':main()
