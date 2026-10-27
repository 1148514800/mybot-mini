"""Frozen DOM operator. Exception-safe cleanup, no reruns; Mock by default."""
import argparse,json,os,socket,time
from pathlib import Path
from scripts.uat_operator.browser_resources import browser_session
from scripts.uat_operator.service import OwnedService
from scripts.uat_operator.ports import OperatorError
from .plan import BATCH,PORT,LIMITS,MESSAGES,STEER,AUTHORIZATION,REQUIRED_AUTHORIZATION
REPO=Path(__file__).resolve().parents[2]

def run(output,chrome,*,live=False,authorization=AUTHORIZATION,fault=None,port=None):
 if live and authorization!=REQUIRED_AUTHORIZATION:raise OperatorError('fresh_GRANT_2_required')
 if live and (fault is not None or port is not None):raise OperatorError('live_override_forbidden')
 os.umask(0o077);output=Path(output).resolve()
 if output.exists():raise OperatorError('new_private_output_required')
 output.mkdir(mode=0o700);batch=BATCH if live else output/'mock-batch'
 if not live:batch.mkdir(mode=0o700)
 provider=json.loads((batch/'prepared.json').read_text())['provider_config_path'] if live else None
 if port is None:
  if live:port=PORT
  else:
   with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 result=dict(mode='LIVE' if live else 'MOCK',real_requests=None if live else 0,port=port,cases={},shutdowns=[],operator_resends=0,cleanup={})
 service=None;case=None
 def save():(output/'browser-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 def verify():
  if not live:return
  from .prepare import verify_frozen
  f=verify_frozen(batch,provider)
  if f['usage']['unsettled']:raise OperatorError('unsettled_request')
  result['last_verify']=f['usage']
 def close_service():
  nonlocal service
  if service is None:return
  try:
   closed=service.close();closed['case']=case
   cleanup=batch/'private'/f'{case}-cleanup.json'
   native=json.loads(cleanup.read_text()) if cleanup.exists() else {};closed['native']=native
   result['shutdowns'].append(closed)
   if closed['was_ready'] and (closed['exit_code']!=0 or not closed['listener_absent'] or not native.get('sdk_streams_closed') or not native.get('lease_released') or not native.get('database_consistent') or native.get('cleanup_uncertain')):raise OperatorError('service_cleanup_unconfirmed')
   # Failed startup is preserved independently, never marked clean exit0.
  except BaseException:
   result['cleanup']['service_shutdown_error']='service_shutdown_failed';raise
  finally:service=None;save()
 try:
  verify()
  with browser_session(chrome,result['cleanup']) as ctx:
   try:
    if fault=='after_context':raise OperatorError('injected_after_context')
    for case in LIMITS:
     verify();status=output/(case+'-service-status.json')
     args=['-m','scripts.streaming_steer_recovery_v3.'+('server' if live else 'mock')]
     args+=['--case',case,'--status-file',str(status)]
     args+=['--batch',str(batch),'--provider-config',provider,'--authorization',authorization] if live else ['--root',str(batch),'--port',str(port)]
     service=OwnedService(args,REPO,port,status,output/(case+'-server.log'))
     try:ready=service.wait_ready()
     except BaseException as exc:
      result['cleanup']['service_start_error']=exc.code if isinstance(exc,OperatorError) else 'service_start_failed';raise
     url='http://127.0.0.1:'+str(port);page=ctx.new_page()
     if fault=='navigation':raise OperatorError('page_navigation_failed')
     page.goto(url);page.locator('#history button').first.wait_for()
     boot=page.request.get(url+'/api/bootstrap').json()
     if not boot.get('streaming_enabled') or boot.get('cleanup_uncertain'):raise OperatorError('application_not_ready')
     with page.expect_response(lambda r:r.url.endswith('/api/conversations') and r.request.method=='POST') as response:page.locator('#new-chat').click()
     if response.value.status!=201:raise OperatorError('new_session_rejected')
     sid=response.value.json()['id'];page.wait_for_timeout(120)
     row=dict(session_id=sid,message_submissions=1,steer_submissions=0,stop_clicks=0,ready_identity_verified=True);result['cases'][case]=row;save()
     page.locator('#message-input').fill(MESSAGES[case]);verify()
     with page.expect_response(lambda r:r.url.endswith('/'+sid+'/messages') and r.request.method=='POST') as response:page.locator('#send').click()
     row['message_http_status']=response.value.status
     if response.value.status!=202:raise OperatorError('message_rejected')
     deadline=time.monotonic()+110;delivered=False
     while True:
      state=page.request.get(url+'/api/conversations/'+sid).json()
      if list((batch/'private').glob(case+'-*-first-delivered.json')) and state['status']=='running':delivered=True;break
      if state['status'] not in ('running','stopping','settling','idle'):break
      if time.monotonic()>deadline:raise OperatorError('first_chunk_deadline')
      page.wait_for_timeout(20)
     row['first_nonterminal_delivered_before_action']=delivered
     if delivered and case=='N01':
      if fault=='steer':raise OperatorError('steer_submission_failed')
      page.locator('#steer-input').fill(STEER[case]);row['steer_submissions']=1;save()
      with page.expect_response(lambda r:r.url.endswith('/steer') and r.request.method=='POST') as response:page.locator('#steer-send').click()
      row['steer_http_status']=response.value.status
      if response.value.status!=200:raise OperatorError('steer_rejected')
     if delivered and case=='N02':
      row['stop_clicks']=1;save()
      with page.expect_response(lambda r:r.url.endswith('/stop') and r.request.method=='POST') as response:page.locator('#stop').click()
      row['stop_http_status']=response.value.status
      if response.value.status!=200:raise OperatorError('stop_rejected')
     deadline=time.monotonic()+180
     while True:
      state=page.request.get(url+'/api/conversations/'+sid).json()
      if state['status'] not in ('running','stopping','settling','idle'):break
      if time.monotonic()>deadline:raise OperatorError('turn_deadline_no_retry')
      page.wait_for_timeout(50)
     page.wait_for_timeout(150);row['status']=state['status'];row['steer_states']=[s['status'] for s in state['steers']]
     settled=batch/'private'/f'{case}-settled.json'
     if not settled.exists():raise OperatorError('settlement_absent')
     row['evidence']=json.loads(settled.read_text())
     if case=='N01':
      text=page.locator('#steer-summary').inner_text();row['not_applied_notice_visible']='未生效' in text and page.locator('#steer-summary').is_visible();row['explicit_next_turn_action_visible']=page.locator('#steer-use').is_visible() if page.locator('#steer-use').count() else '填入下一轮消息' in text
      page.locator('#steer-summary').screenshot(path=str(output/'N01-notice.png'))
     before=row['evidence']['actual_http_attempts'];page.reload();page.locator('#history button').filter(has_text=MESSAGES[case][:12]).first.click();page.wait_for_timeout(2300)
     # Reload + wait beyond finite SSE reconnect. DOM/read-only state only.
     row['refresh_completed']=True;row['refresh_no_resend']=json.loads(settled.read_text())['actual_http_attempts']==before
     if live:
      from .prepare import verify_frozen
      row['ledger_count_after_refresh']=verify_frozen(batch,provider,allow_halt=True)['usage']['http_attempts']
     else:
      from .budget import Ledger
      from .plan import plan_hash
      row['ledger_count_after_refresh']=sum(r['http_attempts'] for r in Ledger(batch/'private/requests.sqlite',plan_hash()).rows())
     if fault=='screenshot':raise OperatorError('page_screenshot_failed')
     page.locator('#activity').screenshot(path=str(output/(case+'-terminal.png')),mask=[page.locator('#timeline'),page.locator('#pins-panel'),page.locator('#contract-panel')]);save()
     close_service();page.close()
     if row['evidence']['protocol_security_halt']:result['stopped_after_case']=case;break
   finally:
    # Service and Context are both cleaned while Playwright's loop is alive.
    import sys
    primary_in_flight=sys.exc_info()[1]
    try:close_service()
    except BaseException:
     if primary_in_flight is None:raise
 except BaseException as exc:
  if result['cleanup'].get('primary_error') is None:result['cleanup']['primary_error']=exc.code if isinstance(exc,OperatorError) else 'operator_failed'
 finally:
  result['physical_reservations']=sum(r.get('evidence',{}).get('physical_reservations',0) for r in result['cases'].values())
  result['actual_http_attempts']=sum(r.get('evidence',{}).get('actual_http_attempts',0) for r in result['cases'].values())
  if live:
   from .prepare import verify_frozen
   try:result['authoritative_usage']=verify_frozen(batch,provider,allow_halt=True)['usage'];result['real_requests']=result['authoritative_usage']['real_requests']
   except BaseException:result['final_verify_error']='integrity_unconfirmed'
  save()
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--chrome',type=Path,required=True);p.add_argument('--live',action='store_true');p.add_argument('--authorization',default=AUTHORIZATION);a=p.parse_args()
 r=run(a.output,a.chrome,live=a.live,authorization=a.authorization)
 print(json.dumps(dict(mode=r['mode'],cases=list(r['cases']),cleanup=r['cleanup'],real_requests=r['real_requests'])))
 if r['cleanup'].get('primary_error') or not r['cleanup'].get('automatic_cleanup_pass'):raise SystemExit(1)
if __name__=='__main__':main()
