"""Real DOM operator. Synthetic approval in Mock only; Live never auto-approves."""
import argparse,json,socket,time
from pathlib import Path
from scripts.uat_operator.browser_resources import browser_session
from scripts.uat_operator.service import OwnedService
from scripts.uat_operator.ports import OperatorError
from .plan import *
REPO=Path(__file__).resolve().parents[2]
def run(output,chrome,*,live=False,authorization=AUTHORIZATION):
 if live and authorization!=REQUIRED_AUTHORIZATION:raise OperatorError('new_GRANT_12_required')
 output=Path(output).resolve()
 if output.exists():raise OperatorError('fresh_output_required')
 output.mkdir(mode=0o700);batch=BATCH if live else output/'mock-batch';r=dict(mode='LIVE' if live else 'MOCK',real_requests=None if live else 0,approval_mode='REAL_HUMAN_REQUIRED' if live else 'SYNTHETIC_APPROVAL',cleanup={},message_submissions=0,synthetic_approval_count=0);service=None
 def save():(output/'browser-result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
 port=PORT;status=output/'status.json'
 try:
  with browser_session(chrome,r['cleanup']) as ctx:
   try:
    args=['-m','scripts.coding_workflow_canary_v1.'+('server' if live else 'mock'),'--status-file',str(status)]
    if live:
     prepared=json.loads((BATCH/'prepared.json').read_text());args+=['--provider-config',prepared['provider_config_path'],'--authorization',authorization]
    else:args+=['--root',str(batch),'--port',str(port)]
    service=OwnedService(args,REPO,port,status,output/'server.log')
    try:service.wait_ready()
    except BaseException as exc:
     r['cleanup']['service_start_error']=exc.code if isinstance(exc,OperatorError) else 'service_start_failed';raise
    page=ctx.new_page();url=f'http://127.0.0.1:{port}';page.goto(url);page.locator('#history button').first.wait_for()
    with page.expect_response(lambda x:x.url.endswith('/api/conversations') and x.request.method=='POST') as response:page.locator('#new-chat').click()
    sid=response.value.json()['id'];r['session_id']=sid;page.wait_for_timeout(150);page.locator('#message-input').fill(MESSAGE);r['message_submissions']=1;save()
    with page.expect_response(lambda x:x.url.endswith('/messages') and x.request.method=='POST') as response:page.locator('#send').click()
    assert response.value.status==202;deadline=time.monotonic()+850;approval_seen=False;preview_seen=False
    while True:
     state=page.request.get(url+'/api/conversations/'+sid).json();preview_seen=preview_seen or page.locator('pre.diff').count()>0
     if page.locator('#approval-dialog').is_visible():
      details=json.loads(page.locator('#approval-details').inner_text());approval_seen=True
      valid=details['tool']=='run_command' and details['execution_mode']=='macos_readonly' and details['os_sandbox'] and details['cwd']=='.' and details['timeout_seconds']<=30 and details['argv'][1:]==COMMAND[1:]
      if not valid:raise OperatorError('unexpected_approval_request')
      r['full_effective_argv_inspected']=True;r['approval_dialog_seen']=True;save()
      if not live and not r['synthetic_approval_count']:
       page.locator('#approval-dialog').screenshot(path=str(output/'approval.png'),mask=[page.locator('#approval-details')]);r['synthetic_approval_count']=1;page.locator('#approve').click()
      # Live: the real human must use this exact native dialog. No nonce API or auto-click.
     if state['status'] not in ('running','waiting_approval','stopping','settling','idle'):break
     if time.monotonic()>deadline:raise OperatorError('turn_timeout_no_retry')
     page.wait_for_timeout(60)
    page.wait_for_timeout(250);r['preview_visible']=preview_seen;r['approval_dialog_seen']=approval_seen;r['controller']=state.get('report');r['status']=state['status'];r['settled']=json.loads((batch/'private/settled.json').read_text())
    before=len(r['settled']['streams']);page.reload();page.locator('#history button').filter(has_text=MESSAGE[:12]).first.click();page.wait_for_timeout(2300)
    from .budget import Ledger
    ledger=Ledger(batch/'private/requests.sqlite',plan_hash());r['refresh_requests']=len(ledger.rows());r['refresh_no_resend']=r['refresh_requests']==before;r['revision_visible']='当前版本' in page.locator('#task-detail').inner_text()
    page.locator('#activity').screenshot(path=str(output/'terminal.png'),mask=[page.locator('#timeline'),page.locator('#contract-panel'),page.locator('#pins-panel')]);save()
   finally:
    import sys
    primary_in_flight=sys.exc_info()[1]
    if service:
     try:
      closed=service.close();r['shutdown']=closed;service=None
      native=batch/'private/cleanup.json';r['native_cleanup']=json.loads(native.read_text()) if native.exists() else {}
      if closed['exit_code']!=0 or not closed['listener_absent'] or not all(r['native_cleanup'].get(k) for k in ('sdk_closed','lease_released','database_consistent')) or r['native_cleanup'].get('cleanup_uncertain'):raise OperatorError('service_cleanup_unconfirmed')
     except BaseException:
      r['cleanup']['service_shutdown_error']='service_shutdown_failed'
      if primary_in_flight is None:raise
     finally:save()
 except BaseException as e:r['primary_error']=e.code if isinstance(e,OperatorError) else 'operator_error'
 finally:save()
 from .score import acceptance
 import asyncio
 if (batch/'private/settled.json').exists() and not r.get('primary_error') and not r.get('settled',{}).get('uncertain',True):
  r['independent_score']=asyncio.run(acceptance(batch/'workspace'));r['physical_requests']=len(ledger.rows());r['actual_http_attempts']=sum(x['http_attempts'] for x in ledger.rows())
  from .score import assess
  from .integrity import IntegrityGate
  IntegrityGate(batch/'workspace',batch/'private/integrity.json').verify()
  r['assessment']=assess(r['settled'],r['independent_score'],mode=r['mode'],shutdown=r['shutdown'],native_cleanup=r['native_cleanup'],browser_cleanup=r['cleanup'],scope_verified=True);save()
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--chrome',required=True);p.add_argument('--live',action='store_true');p.add_argument('--authorization',default=AUTHORIZATION);a=p.parse_args();r=run(a.output,a.chrome,live=a.live,authorization=a.authorization);print(json.dumps(dict(mode=r['mode'],primary_error=r.get('primary_error'),controller=r.get('controller'),cleanup=r['cleanup'],score=r.get('independent_score'))));
 if r.get('primary_error'):raise SystemExit(1)
if __name__=='__main__':main()
