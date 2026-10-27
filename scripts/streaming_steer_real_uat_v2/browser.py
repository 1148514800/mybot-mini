"""Real isolated Chrome operator: mock by default; Live requires a fresh exact grant.
No backend writes for messages/Steer/Stop. No resend or failed Case restart.
"""
import argparse,json,os,subprocess,socket,signal,time,tempfile,shutil
from pathlib import Path
from scripts.local_web_process import _snapshot
from .plan import BATCH,PORT,LIMITS,MESSAGES,STEER,REQUIRED_AUTHORIZATION,AUTHORIZATION
REPO=Path(__file__).resolve().parents[2]

def run(output,chrome,*,live=False,authorization=AUTHORIZATION):
 # Authorization before any private batch/config access or browser/process start.
 if live and authorization!=REQUIRED_AUTHORIZATION:raise RuntimeError('fresh_GRANT_6_required')
 from playwright.sync_api import sync_playwright
 os.umask(0o077);output=Path(output).resolve()
 if output.exists():raise RuntimeError('new_private_output_required')
 output.mkdir(mode=0o700);batch=BATCH if live else output/'mock-batch'
 if not live:batch.mkdir(mode=0o700)
 provider=None
 if live:provider=json.loads((batch/'prepared.json').read_text())['provider_config_path']
 result=dict(mode='LIVE' if live else 'MOCK',real_requests=None if live else 0,cases={},shutdowns=[],operator_resends=0)
 profile=Path(tempfile.mkdtemp(prefix='steer-v2-browser-')).resolve();proc=None;identity=None;ctx=None;arguments=None
 def save():(output/'browser-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 def free(port):
  with socket.socket() as s:return s.connect_ex(('127.0.0.1',port))!=0
 def verify():
  if not live:return
  p=subprocess.run(['uv','run','python','-m','scripts.streaming_steer_real_uat_v2.prepare','verify','--provider-config',provider],cwd=REPO,capture_output=True,text=True)
  if p.returncode:raise RuntimeError('frozen_verify_rejected')
  result['last_verify']=json.loads(p.stdout.strip())
 def capture(port):
  candidates=[int(p) for p,parent in (line.split() for line in subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines()) if int(parent)==proc.pid]+[proc.pid]
  for pid in candidates:
   try:return _snapshot(pid,REPO,arguments,port)
   except (subprocess.CalledProcessError,RuntimeError):continue
  raise RuntimeError('owned_child_unproven')
 def close_service(case,port):
  nonlocal proc
  began=time.monotonic();direct=False
  if proc.poll() is None:proc.send_signal(signal.SIGINT)
  try:code=proc.wait(1)
  except subprocess.TimeoutExpired:
   if identity is None:raise RuntimeError('child_identity_unproven')
   try:now=_snapshot(identity['pid'],REPO,arguments,port)
   except subprocess.CalledProcessError:code=proc.wait(15)
   else:
    if now!=identity:raise RuntimeError('child_identity_changed')
    if identity['pid']!=proc.pid:os.kill(identity['pid'],signal.SIGINT);direct=True
    code=proc.wait(15)
  proc=None
  cleanup_path=batch/'private'/f'{case}-cleanup.json';cleanup=json.loads(cleanup_path.read_text()) if cleanup_path.exists() else {}
  row=dict(case=case,exit_code=code,seconds=time.monotonic()-began,verified_child_sigint=direct,port_released=free(port),native=cleanup)
  result['shutdowns'].append(row);save()
  if code!=0 or not row['port_released'] or not cleanup.get('sdk_streams_closed') or not cleanup.get('lease_released') or not cleanup.get('database_consistent') or cleanup.get('cleanup_uncertain'):raise RuntimeError('cleanup_unconfirmed_no_continue')
 try:
  assert profile==profile.resolve() and not profile.is_symlink() and not list(profile.iterdir()) and profile.stat().st_mode&0o777==0o700
  with sync_playwright() as pw:
   ctx=pw.chromium.launch_persistent_context(str(profile),executable_path=str(chrome),headless=False,chromium_sandbox=True,viewport={'width':1440,'height':1000});assert not ctx.cookies()
   matches=[r for r in subprocess.check_output(['ps','-axo','pid=,uid=,args='],text=True).splitlines() if '--user-data-dir='+str(profile) in r and ' --type=' not in r]
   assert len(matches)==1 and int(matches[0].split()[1])==os.getuid() and not any(x in matches[0] for x in ('--no-sandbox','--disable-web-security','--ignore-certificate-errors'))
   result['browser']=dict(version=ctx.browser.version,headed=True,profile_0700_fresh=True,initial_cookie_jar_empty=True,actual_profile_verified=True);save()
   for case in LIMITS:
    verify()
    if live:port=PORT;arguments=['-m','scripts.streaming_steer_real_uat_v2.server','--case',case,'--batch',str(batch),'--provider-config',provider,'--authorization',authorization]
    else:
     with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
     (batch/'mock-control.json').write_text(json.dumps(dict(case=case)));arguments=['-m','scripts.streaming_steer_real_uat_v2.mock','--root',str(batch),'--port',str(port)]
    assert free(port)
    with (output/(case+'-server.log')).open('w') as log:proc=subprocess.Popen(['uv','run','python',*arguments],cwd=REPO,stdout=log,stderr=log)
    deadline=time.monotonic()+20
    while free(port):
     if proc.poll() is not None or time.monotonic()>deadline:raise RuntimeError('service_start_failed_no_restart')
     time.sleep(.05)
    identity=capture(port);url='http://127.0.0.1:'+str(port);page=ctx.new_page();page.goto(url);page.locator('#history button').first.wait_for()
    with page.expect_response(lambda r:r.url.endswith('/api/conversations') and r.request.method=='POST') as response:page.locator('#new-chat').click()
    assert response.value.status==201;sid=response.value.json()['id'];page.wait_for_timeout(150)
    page.locator('#message-input').fill(MESSAGES[case]);verify()
    row=dict(session_id=sid,message_submissions=1,steer_submissions=0,stop_clicks=0);result['cases'][case]=row;save()
    with page.expect_response(lambda r:r.url.endswith('/'+sid+'/messages') and r.request.method=='POST') as response:page.locator('#send').click()
    row['message_http_status']=response.value.status;assert response.value.status==202
    deadline=time.monotonic()+110;delivered=False
    while True:
     state=page.request.get(url+'/api/conversations/'+sid).json()
     files=list((batch/'private').glob(case+'-*-first-delivered.json'))
     if files and state['status']=='running':delivered=True;break
     if state['status'] not in ('running','stopping','settling','idle'):break
     if time.monotonic()>deadline:raise RuntimeError('first_chunk_deadline')
     page.wait_for_timeout(20)
    row['first_nonterminal_delivered_before_action']=delivered
    if delivered and case in STEER:
     page.locator('#steer-input').fill(STEER[case]);row['steer_submissions']=1;save()
     with page.expect_response(lambda r:r.url.endswith('/steer') and r.request.method=='POST') as response:page.locator('#steer-send').click()
     row['steer_http_status']=response.value.status
     if response.value.status==200:row['steer_acceptance']={k:v for k,v in response.value.json().items() if k in ('steer_id','turn_id','source_event_id','status')}
    if delivered and case=='T03':
     row['stop_clicks']=1;save()
     with page.expect_response(lambda r:r.url.endswith('/stop') and r.request.method=='POST') as response:page.locator('#stop').click()
     row['stop_http_status']=response.value.status
    deadline=time.monotonic()+300
    while True:
     state=page.request.get(url+'/api/conversations/'+sid).json()
     if state['status'] not in ('running','stopping','settling','idle'):break
     if time.monotonic()>deadline:raise RuntimeError('turn_deadline_no_retry')
     page.wait_for_timeout(60)
    page.wait_for_timeout(200);row['status']=state['status'];row['steer_states']=[s['status'] for s in state['steers']]
    settled_path=batch/'private'/f'{case}-settled.json'
    if not settled_path.exists():raise RuntimeError('settlement_absent')
    settled=json.loads(settled_path.read_text());row['evidence']=settled
    if case=='T02':
     page.reload();page.locator('#history button').filter(has_text='请用四句话解释Python列表推导式').first.click();page.wait_for_timeout(200)
     row['refresh_completed']=True
    page.locator('#activity').screenshot(path=str(output/(case+'-terminal.png')),mask=[page.locator('#timeline'),page.locator('#pins-panel'),page.locator('#contract-panel')]);save()
    close_service(case,port);page.close()
    if settled['protocol_security_halt']:result['stopped_after_case']=case;break
   result['physical_reservations']=sum(r.get('evidence',{}).get('physical_reservations',0) for r in result['cases'].values())
   result['actual_http_attempts']=sum(r.get('evidence',{}).get('actual_http_attempts',0) for r in result['cases'].values())
   if live:result['real_requests']=result['physical_reservations']
   ctx.close();ctx=None
 except BaseException as exc:result['operator_error_type']=type(exc).__name__;save();raise
 finally:
  if proc is not None:
   try:close_service(case,port)
   except BaseException as exc:result['cleanup_error_type']=type(exc).__name__
  if ctx is not None:ctx.close()
  shutil.rmtree(profile);result['profile_removed']=not profile.exists();save()
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--chrome',type=Path,required=True);p.add_argument('--live',action='store_true');p.add_argument('--authorization',default=AUTHORIZATION);a=p.parse_args();r=run(a.output,a.chrome,live=a.live,authorization=a.authorization);print(json.dumps(dict(mode=r['mode'],cases=list(r['cases']),profile_removed=r['profile_removed'],real_requests=r['real_requests'])))
if __name__=='__main__':main()
