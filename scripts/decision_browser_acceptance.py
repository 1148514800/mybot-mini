"""Headed Chrome synthetic acceptance. Optional, isolated Playwright environment.

uv run --no-project --with playwright python scripts/decision_browser_acceptance.py
No provider configuration is loaded; only a new private temporary root is used.
"""
import pathlib,tempfile,json,os,subprocess,time,signal,shutil,socket,hashlib,traceback,threading
from http.server import BaseHTTPRequestHandler,HTTPServer
from playwright.sync_api import sync_playwright
os.umask(0o077)
R=pathlib.Path(__file__).resolve().parents[1];ROOT=pathlib.Path(tempfile.mkdtemp(prefix='decision-browser-')).resolve();ROOT.chmod(0o700);pathlib.Path('/tmp/decision-browser-root').write_text(str(ROOT));URL='http://127.0.0.1:8898';CHROME='/Volumes/move-disk/app/Google Chrome.app/Contents/MacOS/Google Chrome';proc=None;ctx=None;profile=None;result={'real_model_requests':0,'checks':{},'cleanup':{}}
PINS=['笔记数据只能在本地处理。','不允许自动删除原始笔记。'];OLD='索引文件命名为index.md。';NEW='索引文件命名为catalog.md。'
def out(text):print(text,flush=True)
def listening():
 with socket.socket() as s:return s.connect_ex(('127.0.0.1',8898))==0
def start():
 global proc
 assert not listening();log=(ROOT/'server.log').open('a');proc=subprocess.Popen(['uv','run','python','-m','scripts.decision_browser_server','--root',str(ROOT),'--port','8898'],cwd=R,stdout=log,stderr=subprocess.STDOUT);log.close()
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
def count():return len((ROOT/'synthetic-requests.jsonl').read_text().splitlines()) if (ROOT/'synthetic-requests.jsonl').exists() else 0
def latest():return json.loads((ROOT/'synthetic-requests.jsonl').read_text().splitlines()[-1])
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
def pin(p,sid,text,old=None):
 p.get_by_role('button',name='固定此消息片段',exact=True).last.click();p.locator('#pin-dialog').wait_for(state='visible');p.locator('#pin-quote').fill(text);p.locator('#pin-category').select_option('user_constraint')
 if old:p.locator('#pin-replace').select_option(old['id'])
 with p.expect_response(lambda r:r.url==URL+'/api/conversations/'+sid+'/pins' and r.request.method=='POST') as r:p.locator('#pin-confirm').click()
 assert r.value.status==200;p.locator('#pin-dialog').wait_for(state='hidden');return next(x for x in get(p,sid)['pins'] if x['content']==text and x['status']=='active')
def expand(p):
 if p.locator('#pins-panel').get_attribute('open') is None:p.locator('#pins-panel > summary').click()
def revoke(p,sid):
 expand(p);p.get_by_role('button',name='撤销固定',exact=True).click();p.locator('#data-confirm').wait_for(state='visible')
 with p.expect_response(lambda r:r.url.endswith('/revoke') and r.request.method=='POST') as r:p.locator('#data-approve').click()
 assert r.value.status==200

# A/B same-Origin probe: no MyBot cookies or user profile access.
class Probe(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b'<button id="write" onclick="document.cookie=\'decision_probe=1; Path=/\';localStorage.setItem(\'decision_probe\',\'1\')">probe</button>')
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
   state=lambda p:p.evaluate("({cookie:document.cookie,local:localStorage.getItem('decision_probe')})")
   assert state(pages[0])=={'cookie':'decision_probe=1','local':'1'};assert state(pages[1])=={'cookie':'','local':None}
   pages[0].evaluate("document.cookie='decision_probe=; Max-Age=0; Path=/';localStorage.removeItem('decision_probe')")
   pages[1].locator('#write').click();assert state(pages[0])=={'cookie':'','local':None};assert state(pages[1])=={'cookie':'decision_probe=1','local':'1'}
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
  sid=new(p);send(p,sid,''.join(PINS));[pin(p,sid,t) for t in PINS];expand(p)
  assert '推断不是宿主已确认事项' in p.locator('#pins-notice').inner_text();assert all(not x['needs_review'] for x in get(p,sid)['pins']);s=send(p,sid,'继续设计并讨论可选方案。')
  assert '永久保留是已确定要求' in p.locator('#messages').inner_text();assert {x['original_quote'] for x in s['decisions']['items']}==set(PINS);assert '永久保留' not in p.locator('#pins-list').inner_text();assert all(x['source_verified'] for x in s['decisions']['items']);result['checks']['A_wrong_model_text_not_trusted']=True
  expand(p);p.locator('#pins-list details summary').first.click();time.sleep(1);p.screenshot(animations='disabled',path=str(ROOT/'A-trusted-vs-model.png'))
  for i in range(7):send(p,sid,f'公开合成长对话第{i+1}轮，继续讨论。')
  s=get(p,sid);assert all(t in str(latest()) for t in PINS);result['checks']['D_cross_six_turn_pins']=True
  sidB=new(p);send(p,sidB,OLD);old=pin(p,sidB,OLD);b1=get(p,sidB)['decisions']['boundary'];send(p,sidB,NEW);current=pin(p,sidB,NEW,old);s=get(p,sidB);b2=s['decisions']['boundary'];ds={x['pin_id']:x for x in s['decisions']['items']};assert ds[old['id']]['valid_until']==b2 and ds[current['id']]['valid_from']==b2;expand(p);assert '历史曾有效，已被替换' in p.locator('#pins-list').inner_text();time.sleep(1);p.screenshot(animations='disabled',path=str(ROOT/'B-replacement-history.png'));result['checks']['B_atomic_replacement_history']=True
  revoke(p,sidB);s=get(p,sidB);assert not any(x['status_at_boundary']=='active' for x in s['decisions']['items']);assert '历史曾有效，已撤销' in p.locator('#pins-list').inner_text();time.sleep(1);p.screenshot(animations='disabled',path=str(ROOT/'C-revoked-history.png'));result['checks']['C_revoke_current_empty']=True
  states={x:get(p,x) for x in [sid,sidB]};before=count();p.close();stop();start();p=ctx.new_page();p.goto(URL);p.locator('#history button').filter(has_text=states[sid]['title']).click()
  for x in states:
   restored=get(p,x);assert restored['decisions']==states[x]['decisions'];assert restored['pins']==states[x]['pins'];assert restored['messages']==states[x]['messages'];assert restored['report'] is None and restored['contract'] is None and restored['approval'] is None
  assert before==count();send(p,sid,'重启后继续，尚未确认的建议保持待确认。');assert all(t in str(latest()) for t in PINS);result['checks']['D_restart_timeline_pins_without_authority']=True
  expand(p);time.sleep(1);p.screenshot(animations='disabled',path=str(ROOT/'D-restarted.png'))
  requests=[json.loads(l) for l in (ROOT/'synthetic-requests.jsonl').read_text().splitlines()];refs=[m for r in requests for m in r['messages'] if (m.get('content') or '').startswith('[宿主生成的固定事项生命周期参考')]
  from_size=lambda ms:len(json.dumps({'messages':ms},ensure_ascii=False).encode())+256+32*len(ms)
  result['reference_measurement']={'standalone_estimate_min':min(from_size([m]) for m in refs),'standalone_estimate_max':max(from_size([m]) for m in refs),'method':'UTF8 JSON bytes + 256 framing + 32 per message; estimate, not deployment tokens','requests_with_reference':sum(any(m in refs for m in r['messages']) for r in requests)}
  result['synthetic_requests']=count();result['checks']['real_api_calls_zero']=True;p.close();stop();ctx.close();ctx=None;shutil.rmtree(profile);profile=None;result['status']='PASS'
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
