"""Streaming & Steer headed Chrome SDK MockTransport acceptance. Optional, isolated Playwright environment.

uv run --no-project --with playwright python scripts/decision_browser_acceptance.py
No provider configuration is loaded; only a new private temporary root is used.
"""
import pathlib,tempfile,json,os,subprocess,time,signal,shutil,socket,hashlib,traceback,threading
from http.server import BaseHTTPRequestHandler,HTTPServer
from playwright.sync_api import sync_playwright
os.umask(0o077)
R=pathlib.Path(__file__).resolve().parents[1];ROOT=pathlib.Path(tempfile.mkdtemp(prefix='streaming-browser-')).resolve();ROOT.chmod(0o700);pathlib.Path('/tmp/streaming-browser-root').write_text(str(ROOT));URL='http://127.0.0.1:8899';CHROME='/Volumes/move-disk/app/Google Chrome.app/Contents/MacOS/Google Chrome';proc=None;ctx=None;profile=None;result={'real_model_requests':0,'checks':{},'cleanup':{}}
PINS=['笔记数据只能在本地处理。','不允许自动删除原始笔记。'];OLD='索引文件命名为index.md。';NEW='索引文件命名为catalog.md。'
def out(text):print(text,flush=True)
def listening():
 with socket.socket() as s:return s.connect_ex(('127.0.0.1',8899))==0
def start():
 global proc
 assert not listening();log=(ROOT/'server.log').open('a');proc=subprocess.Popen(['uv','run','python','-m','scripts.streaming_browser_server','--root',str(ROOT),'--port','8899'],cwd=R,stdout=log,stderr=subprocess.STDOUT);log.close()
 until=time.monotonic()+20
 while not listening():
  assert proc.poll() is None
  if time.monotonic()>until:raise TimeoutError('server startup')
  time.sleep(.1)
def stop():
 global proc
 if proc:
  proc.send_signal(signal.SIGINT);assert proc.wait(timeout=20)==0;proc=None;assert not listening()
 code="from pathlib import Path;from mybot.workspace_lease import WorkspaceLease;import sys;lease=WorkspaceLease(Path(sys.argv[1]));lease.acquire();lease.release()"
 subprocess.run(['uv','run','python','-c',code,str(ROOT/'workspace')],cwd=R,check=True,capture_output=True)
def get(p,sid):
 r=p.request.get(URL+'/api/conversations/'+sid);assert r.status==200;return r.json()
def count():return len((ROOT/'sdk-requests.jsonl').read_text().splitlines()) if (ROOT/'sdk-requests.jsonl').exists() else 0
def latest():return json.loads((ROOT/'sdk-requests.jsonl').read_text().splitlines()[-1])
def send(p,sid,text):
 p.locator('#message-input').fill(text)
 with p.expect_response(lambda r:r.url==URL+'/api/conversations/'+sid+'/messages' and r.request.method=='POST') as r:p.locator('#send').click()
 assert r.value.status==202
 until=time.monotonic()+25
 while True:
  s=get(p,sid)
  if s['status'] not in ['pending','running','stopping','settling','waiting_approval']:break
  assert time.monotonic()<until;time.sleep(.15)
 assert s['status']=='completed',s['status'];assert s['approval'] is None
 until=time.monotonic()+10
 while not p.locator('#new-chat').is_enabled():
  assert time.monotonic()<until;time.sleep(.1)
 return s
def new(p):
 with p.expect_response(lambda r:r.url==URL+'/api/conversations' and r.request.method=='POST') as r:p.locator('#new-chat').click()
 assert r.value.status==201;return r.value.json()['id']
# A/B same-Origin probe: no MyBot cookies or user profile access.
class Probe(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b'<button id="write" onclick="document.cookie=\'streaming_probe=1; Path=/\';localStorage.setItem(\'streaming_probe\',\'1\')">probe</button>')
 def log_message(self,*a):pass
try:
 with sync_playwright() as pw:
  probe=HTTPServer(('127.0.0.1',0),Probe);thread=threading.Thread(target=probe.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(probe.server_port)
  profiles=[pathlib.Path(tempfile.mkdtemp(prefix=x,dir=ROOT)) for x in ('probe-A-','probe-B-')];contexts=[]
  try:
   for d in profiles:contexts.append(pw.chromium.launch_persistent_context(str(d),executable_path=CHROME,headless=False,chromium_sandbox=True))
   pages=[c.new_page() for c in contexts]
   for p in pages:p.goto(origin)
   pages[0].locator('#write').click()
   state=lambda p:p.evaluate("({cookie:document.cookie,local:localStorage.getItem('streaming_probe')})")
   assert state(pages[0])=={'cookie':'streaming_probe=1','local':'1'};assert state(pages[1])=={'cookie':'','local':None}
   pages[0].evaluate("document.cookie='streaming_probe=; Max-Age=0; Path=/';localStorage.removeItem('streaming_probe')")
   pages[1].locator('#write').click();assert state(pages[0])=={'cookie':'','local':None};assert state(pages[1])=={'cookie':'streaming_probe=1','local':'1'}
   commands=subprocess.check_output(['ps','-axo','pid=,uid=,command='],text=True)
   assert profiles[0]!=profiles[1] and all('--user-data-dir='+str(d) in commands for d in profiles)
   result['checks']['dual_profile_cookie_localstorage_bidirectional']=True
  finally:
   for c in contexts:c.close()
   probe.shutdown();probe.server_close();thread.join(timeout=3)
   for d in profiles:shutil.rmtree(d)
  profile=pathlib.Path(tempfile.mkdtemp(prefix='uat-profile-',dir=ROOT));assert not profile.is_symlink() and not list(profile.iterdir())
  ctx=pw.chromium.launch_persistent_context(str(profile),executable_path=CHROME,headless=False,chromium_sandbox=True,viewport={'width':1560,'height':1080});assert not ctx.cookies()
  matches=[l for l in subprocess.check_output(['ps','-axo','pid=,uid=,command='],text=True).splitlines() if '--user-data-dir='+str(profile) in l and '--type=' not in l];assert len(matches)==1 and '--no-sandbox' not in matches[0] and int(matches[0].split()[1])==os.getuid()
  result['browser']={'playwright_version':__import__('importlib.metadata',fromlist=['version']).version('playwright'),'headed':True,'version':ctx.browser.version,'new_0700_profile':profile.stat().st_mode&0o777==0o700,'launch_argument_verified':True,'profile_path_sha256':hashlib.sha256(str(profile).encode()).hexdigest()}
  start();p=ctx.new_page();p.goto(URL);p.locator('#history button').first.wait_for()
  def begin(sid,text):
   p.locator('#message-input').fill(text)
   with p.expect_response(lambda r:r.url==URL+'/api/conversations/'+sid+'/messages' and r.request.method=='POST') as response:p.locator('#send').click()
   assert response.value.status==202
  def done(sid):
   until=time.monotonic()+30
   while True:
    state=get(p,sid)
    if state['status'] not in ['running','pending','stopping','settling','waiting_approval']:return state
    assert time.monotonic()<until;time.sleep(.1)
  def steer(text):
   p.locator('#steer-input').fill(text)
   with p.expect_response(lambda r:r.url.endswith('/steer') and r.request.method=='POST') as response:p.locator('#steer-send').click()
   assert response.value.status==200
  def screenshot(name):time.sleep(.3);p.screenshot(animations='disabled',path=str(ROOT/(name+'.png')))
  sidA=new(p);begin(sidA,'场景A：真实中文和Markdown流式展示。');p.locator('#stream-body').get_by_text('早期中文已经出现。',exact=True).wait_for();state=get(p,sidA);assert state['status']=='running';assert state['resources']['physical_requests']==1 and state['resources']['http_dispatch_attempts']==1;assert sum(m['role']=='assistant' for m in state['messages'])==0;assert p.locator('#stream-label').inner_text().startswith('生成中');screenshot('A-before-final');s=done(sidA);assert s['resources']['physical_requests']==1 and s['resources']['http_dispatch_attempts']==1;assert p.evaluate('window.syntheticXss === undefined');result['checks']['A_incremental_before_final']=True
  sidB=new(p);begin(sidB,'场景B：等待完整工具调用之前接收补充。');until=time.monotonic()+10
  while p.locator('#steer-form').is_hidden():
   assert time.monotonic()<until;time.sleep(.05)
  first=latest();steer('先不要修改文件，先检查测试。');s=done(sidB);assert s['steers'][0]['status']=='applied';requests=[json.loads(l) for l in (ROOT/'sdk-requests.jsonl').read_text().splitlines()];assert requests[-2]==first;assert '先不要修改' in str(requests[-1]['messages']);assert 'not_executed_pending_user_steer' in str(requests[-1]['messages']);assert not any(e['type']=='tool_started' for e in s['events']);assert s['resources']['physical_requests']==2;result['checks']['B_steer_skips_tools_original_request_unchanged']=True;screenshot('B-applied')
  sidC=new(p);begin(sidC,'场景C：正在生成最终文本，没有下一模型步骤。');steer('这条补充不能影响已经发出的请求。');s=done(sidC);assert s['steers'][0]['status']=='not_applied';assert s['resources']['physical_requests']==1;p.get_by_role('button',name='填入下一轮消息',exact=True).wait_for();before=count();p.get_by_role('button',name='填入下一轮消息',exact=True).click();assert p.locator('#message-input').input_value()==s['steers'][0]['text'];assert count()==before;result['checks']['C_no_next_step_no_extra_request']=True;screenshot('C-not-applied')
  sidD=new(p);begin(sidD,'场景D：断流后部分工具参数不得执行。');s=done(sidD);assert s['status']=='provider_error';assert s['stream_preview']['status']=='provider_error';assert '未完成' in s['messages'][-1]['content'];assert not any(e['type']=='tool_started' for e in s['events']);result['checks']['D_broken_stream_incomplete_no_tool']=True;screenshot('D-incomplete')
  sidE=new(p);begin(sidE,'场景E：流式期间真实断开浏览器网络后重连。');p.locator('#stream-body').get_by_text('重连第00行。',exact=True).wait_for();before=count();ctx.set_offline(True);time.sleep(.8);ctx.set_offline(False);s=done(sidE);assert count()==before;assert s['resources']['physical_requests']==1;p.locator('#messages').get_by_text('重连第00行。',exact=False).wait_for();text=p.locator('#messages').inner_text();assert text.count('重连第00行。')==1;result['checks']['E_real_disconnect_reconnect_no_duplicate_or_replay']=True;screenshot('E-reconnected')
  sidF=new(p);begin(sidF,'场景F：合成命令等待审批，不能通过Steer绕过。');p.locator('#approval-dialog').wait_for(state='visible');assert p.locator('#steer-send').is_disabled();s=get(p,sidF);assert s['status']=='waiting_approval';p.locator('#deny').click();s=done(sidF);assert not any(e.get('metadata',{}).get('executed') is True for e in s['events']);result['checks']['F_approval_not_bypassed']=True;screenshot('F-denied')
  sidH=new(p);begin(sidH,'场景H：真实点击停止正在消费的流。');p.locator('#stream-body').get_by_text('可取消第0行。',exact=True).wait_for();steer('停止后这条补充必须失效。');p.locator('#stop').click();s=done(sidH);assert s['status']=='cancelled';assert s['steers'][0]['status']=='discarded_on_stop';result['checks']['H_stop_closes_stream_discards_steer']=True;screenshot('H-cancelled')
  before=count();p.close();stop();start();p=ctx.new_page();p.goto(URL);p.locator('#history button').filter(has_text='场景C').click();restored=get(p,sidC);assert restored['steers'][0]['status']=='not_applied';assert restored['stream_preview']=={} and restored['approval'] is None and restored['report'] is None and restored['contract'] is None;assert count()==before;p.locator('#history button').filter(has_text='场景H').click();assert get(p,sidH)['steers'][0]['status']=='discarded_on_stop';assert count()==before;result['checks']['G_restart_no_stream_or_steer_tool_replay']=True;screenshot('G-restored')
  result['synthetic_requests']=count();result['sdk_http_attempts']=count();result['stream_close_observations']=len((ROOT/'stream-closes.log').read_text().splitlines());result['status']='PASS';p.close();stop();ctx.close();ctx=None;shutil.rmtree(profile);profile=None
except BaseException as e:
 result['status']='FAIL';result['error_type']=type(e).__name__;result['error']=str(e)[:350];(ROOT/'error-private.txt').write_text(traceback.format_exc());out('browser FAILED '+type(e).__name__+': '+str(e)[:150])
finally:
 try:
  if proc:stop()
  if ctx:ctx.close()
  if profile:shutil.rmtree(profile)
  result['cleanup']={'own_server_stopped':not listening(),'own_profile_removed':profile is None or not profile.exists(),'lease_reacquired_after_each_stop':True}
 except Exception as e:result['cleanup_error']=type(e).__name__
 (ROOT/'browser-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));out(str(ROOT));out(result['status'])
