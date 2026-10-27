"""Optional isolated headed Playwright acceptance; no actual provider is reachable.

uv run --no-project --with playwright python scripts/stream_protocol_browser.py
"""
import tempfile,pathlib,os,subprocess,time,json,socket,signal,shutil,sqlite3,hashlib
from playwright.sync_api import sync_playwright
os.umask(0o077)
REPO=pathlib.Path(__file__).resolve().parents[1];ROOT=pathlib.Path(tempfile.mkdtemp(prefix='legacy-steer-chrome-')).resolve();ROOT.chmod(0o700)
pathlib.Path('/tmp/legacy-steer-chrome-root').write_text(str(ROOT));profile=ROOT/'profile';profile.mkdir(mode=0o700);DATA=ROOT/'service';DATA.mkdir(mode=0o700)
with socket.socket() as s:s.bind(('127.0.0.1',0));PORT=s.getsockname()[1]
URL='http://127.0.0.1:'+str(PORT);CHROME='/Volumes/move-disk/app/Google Chrome.app/Contents/MacOS/Google Chrome';proc=None;identity=None
results=dict(launcher_stdin_is_tty=os.isatty(0),real_requests=0,cases={},shutdowns=[],profile_initially_empty=None)
def save():
 (ROOT/'result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
def count():return len((DATA/'sdk-requests.jsonl').read_text().splitlines()) if (DATA/'sdk-requests.jsonl').exists() else 0
def start():
 global proc,identity
 with socket.socket() as s:assert s.connect_ex(('127.0.0.1',PORT))!=0
 log=(ROOT/'server.log').open('a');proc=subprocess.Popen(['uv','run','python','-m','scripts.stream_protocol_server','--root',str(DATA),'--port',str(PORT)],cwd=REPO,stdout=log,stderr=log);log.close()
 deadline=time.monotonic()+15
 while True:
  with socket.socket() as s:
   if s.connect_ex(('127.0.0.1',PORT))==0:
    identity=__import__('local_web_process').capture(proc,REPO,'scripts.stream_protocol_server',DATA,PORT);return
  assert proc.poll() is None and time.monotonic()<deadline;time.sleep(.05)
def stop(label):
 global proc
 stopped=__import__('local_web_process').stop(proc,identity,REPO,DATA,PORT);proc=None;code=stopped['exit_code'];elapsed=stopped['seconds'];assert code==0 and elapsed<8
 with socket.socket() as s:assert s.connect_ex(('127.0.0.1',PORT))!=0
 check=subprocess.run(['uv','run','python','-c','from mybot.workspace_lease import WorkspaceLease; from pathlib import Path; import sys; l=WorkspaceLease(Path(sys.argv[1])).acquire(); l.release()',str(DATA/'workspace')],cwd=REPO,capture_output=True);assert check.returncode==0
 results['shutdowns'].append(dict(label=label,**stopped,lease_released=True,port_released=True));save()
with sync_playwright() as pw:
 ctx=pw.chromium.launch_persistent_context(str(profile),executable_path=CHROME,headless=False,chromium_sandbox=True)
 try:
  assert not ctx.cookies();results['profile_initially_empty']=True;results['chrome']=ctx.browser.version;results['headed']=True
  launch=[l for l in subprocess.check_output(['ps','-axo','pid=,uid=,args='],text=True).splitlines() if '--user-data-dir='+str(profile) in l and ' --type=' not in l];assert len(launch)==1;assert int(launch[0].split()[1])==os.getuid();results['actual_profile_verified']=True
  page=ctx.new_page();start();page.goto(URL);page.locator('#history button').first.wait_for();page.bring_to_front()
  def state(sid):return page.request.get(URL+'/api/conversations/'+sid).json()
  def send(message):
   with page.expect_response(lambda r:r.url.endswith('/api/conversations') and r.request.method=='POST') as r:page.locator('#new-chat').click()
   assert r.value.status==201;sid=r.value.json()['id'];page.wait_for_timeout(150);page.locator('#message-input').fill(message)
   with page.expect_response(lambda r:r.url.endswith('/conversations/'+sid+'/messages') and r.request.method=='POST') as r:page.locator('#send').click()
   assert r.value.status==202;return sid
  def terminal(sid):
   deadline=time.monotonic()+20
   while True:
    s=state(sid)
    if s['status'] not in ('running','stopping','settling','idle'):page.wait_for_timeout(250);return s
    assert time.monotonic()<deadline;page.wait_for_timeout(50)
  def visible():
   deadline=time.monotonic()+10
   while True:
    if page.locator('#stream-preview').is_visible() and page.locator('#stream-body').inner_text() not in ('','等待可安全展示的文本…'):return
    assert time.monotonic()<deadline;page.wait_for_timeout(30)
  sidA=send('合成A标准流');visible();page.locator('#stream-preview').screenshot(path=str(ROOT/'A-preview.png'));s=terminal(sidA);assert s['status']=='completed';results['cases']['A']=dict(status='PASS',sdk_requests=count(),complete=True)
  beforeH=count();sidH=send('合成H终轮补充');visible();page.locator('#steer-input').fill('本轮若无下一请求，不要声称已应用。')
  with page.expect_response(lambda r:r.url.endswith('/steer') and r.request.method=='POST') as r:page.locator('#steer-send').click()
  assert r.value.status==200 and r.value.json()['status']=='queued';s=terminal(sidH);assert s['steers'][-1]['status']=='not_applied' and count()==beforeH+1
  page.locator('#steer-summary').screenshot(path=str(ROOT/'H-not-applied.png'));results['cases']['H']=dict(status='PASS',queued=True,not_applied=True,no_extra_request=True)
  sidB=send('合成B重复终态');visible();s=terminal(sidB);assert s['status']=='provider_error';assert s['stream_preview']['error_code']=='stream_duplicate_finish';assert '协议结构不兼容' in page.locator('#stream-label').inner_text();page.locator('#stream-preview').screenshot(path=str(ROOT/'B-protocol.png'));results['cases']['B']=dict(status='PASS',error_code=s['stream_preview']['error_code'],complete=False)
  sidD=send('合成D完整工具');s=terminal(sidD);assert s['status']=='completed';assert 'SYNTHETIC-LOCAL-42' in s['messages'][-1]['content']
  with sqlite3.connect(DATA/'private/events.sqlite3') as db:before=db.execute('select count(*) from tools').fetchone()[0];names=[r[0] for r in db.execute('select name from tools')]
  assert names==['read_file'];sidD2=send('合成D2不完整参数');s=terminal(sidD2);assert s['status']=='provider_error'
  with sqlite3.connect(DATA/'private/events.sqlite3') as db:assert db.execute('select count(*) from tools').fetchone()[0]==before
  results['cases']['D']=dict(status='PASS',executed_tools=names,incomplete_tool_executed=False)
  sidE=send('合成E安全边界补充');visible();page.locator('#steer-input').fill('优先检查公开说明，不要执行旧工具。')
  with page.expect_response(lambda r:r.url.endswith('/steer') and r.request.method=='POST') as r:page.locator('#steer-send').click()
  assert r.value.status==200 and r.value.json()['status']=='queued';s=terminal(sidE);assert s['steers'][-1]['status']=='applied';page.locator('#steer-summary').screenshot(path=str(ROOT/'E-steer.png'))
  bodies=[json.loads(l) for l in (DATA/'sdk-requests.jsonl').read_text().splitlines()];erows=[b for b in bodies if any(m.get('content')=='合成E安全边界补充' for m in b['messages'])];assert len(erows)==2;assert '优先检查公开说明' not in json.dumps(erows[0],ensure_ascii=False);assert '优先检查公开说明' in json.dumps(erows[1],ensure_ascii=False);assert 'not_executed_pending_user_steer' in json.dumps(erows[1]);results['cases']['E']=dict(status='PASS',queued=True,applied=True,original_unchanged=True,next_request_steer=True,old_tool_skipped=True)
  sidC=send('合成C关闭进行中流');visible();assert state(sidC)['status']=='running';before=count();stop('C-open-EventSource-active-stream');results['cases']['C']=dict(status='PASS',browser_kept_open=True)
  start();page.goto(URL);page.wait_for_timeout(500);assert count()==before
  # Restore via actual history button; this never submits a model request.
  page.locator('#history button').filter(has_text='合成C关闭进行中流').click();page.wait_for_timeout(300);s=state(sidC);assert s['status'] in ('cancelled','interrupted');assert not s['steers'];assert not s['stream_preview'];assert not any(m['role']=='assistant' for m in s['messages']);assert count()==before
  results['cases']['G']=dict(status='PASS',session_restored=True,no_replay=True,no_partial_complete=True)
  sidF=send('合成F触发模拟HALT');s=terminal(sidF);assert s['status']=='provider_error'
  with sqlite3.connect(DATA/'synthetic-ledger.sqlite') as db:assert db.execute("select value from meta where key='halt'").fetchone()
  before=count();page.locator('#message-input').fill('合成A HALT后禁止新请求')
  with page.expect_response(lambda r:r.url.endswith('/messages') and r.request.method=='POST') as r:page.locator('#send').click()
  assert r.value.status==409;assert count()==before;page.locator('#notice').screenshot(path=str(ROOT/'F-halt.png'));stop('F-halted-open-EventSource');results['cases']['F']=dict(status='PASS',new_request_refused=True,halt_preserved=True)
  with sqlite3.connect(DATA/'synthetic-ledger.sqlite') as db:assert db.execute("select value from meta where key='halt'").fetchone()[0]=='synthetic_protocol_failure'
  results['mock_http_requests']=count();results['mock_sdk_request_hashes']=[hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest() for v in [json.loads(l) for l in (DATA/'sdk-requests.jsonl').read_text().splitlines()]];results['mock_stream_closes']=len((DATA/'stream-closes.jsonl').read_text().splitlines())
 except BaseException as e:
  results['error_type']=type(e).__name__;save();raise
 finally:
  ctx.close();shutil.rmtree(profile);results['profile_removed']=not profile.exists()
  if proc is not None:stop('finally')
  save()
print(json.dumps(results,ensure_ascii=False),flush=True)
