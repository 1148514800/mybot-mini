"""Offline headed Chrome rehearsal; separate mock batch per scenario, no Live switch.
Run via uv run --no-project --with playwright python -m scripts.stream_diagnostic_canary.browser.
"""
import argparse,json,os,shutil,socket,subprocess,tempfile,time
from pathlib import Path
from scripts.local_web_process import capture,stop
from .plan import MESSAGE
MODULE='scripts.stream_diagnostic_canary.mock'
REPO=Path(__file__).resolve().parents[2]
def run(output,chrome):
 from playwright.sync_api import sync_playwright
 os.umask(0o077);output=Path(output).resolve()
 if output.exists():raise RuntimeError('new_output_required')
 output.mkdir(mode=0o700);results={'real_requests':0,'cases':{},'shutdowns':[]}
 profile=Path(tempfile.mkdtemp(prefix='canary-chrome-')).resolve();proc=None;ctx=None
 try:
  with sync_playwright() as pw:
   ctx=pw.chromium.launch_persistent_context(str(profile),executable_path=str(chrome),headless=False,chromium_sandbox=True)
   assert not ctx.cookies();results.update(headed=True,browser=ctx.browser.version,initial_cookie_jar_empty=True)
   matches=[x for x in subprocess.check_output(['ps','-axo','pid=,uid=,args='],text=True).splitlines() if '--user-data-dir='+str(profile) in x and ' --type=' not in x]
   assert len(matches)==1 and int(matches[0].split()[1])==os.getuid();results['actual_profile_verified']=True
   for mode in ('standard','duplicate'):
    root=output/mode;root.mkdir(mode=0o700);(root/'mode.txt').write_text(mode)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    with (root/'server.log').open('w') as log:proc=subprocess.Popen(['uv','run','python','-m',MODULE,'--root',str(root),'--port',str(port)],cwd=REPO,stdout=log,stderr=log)
    deadline=time.monotonic()+20
    while True:
     with socket.socket() as s:
      if s.connect_ex(('127.0.0.1',port))==0:break
     assert proc.poll() is None and time.monotonic()<deadline;time.sleep(.05)
    identity=capture(proc,REPO,MODULE,root,port);url='http://127.0.0.1:'+str(port)
    page=ctx.new_page();page.goto(url);page.locator('#history button').first.wait_for()
    with page.expect_response(lambda r:r.url.endswith('/api/conversations') and r.request.method=='POST') as response:page.locator('#new-chat').click()
    assert response.value.status==201;sid=response.value.json()['id'];page.wait_for_timeout(200)
    # Read-only DOM timing, same performance.now clock. No backend or message mutation.
    page.evaluate('''() => { window.canaryTiming={}; document.querySelector('#send').addEventListener('click',()=>{window.canaryTiming.submit=performance.now()}, {once:true}); new MutationObserver(()=>{const el=document.querySelector('#stream-body');const panel=document.querySelector('#stream-preview');if(window.canaryTiming.submit && !window.canaryTiming.visible && el && panel && !panel.hidden && el.textContent.trim() && !el.textContent.includes('等待可安全展示的文本'))window.canaryTiming.visible=performance.now()}).observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true}); }''')
    page.locator('#message-input').fill(MESSAGE)
    with page.expect_response(lambda r:r.url.endswith('/'+sid+'/messages') and r.request.method=='POST') as response:page.locator('#send').click()
    assert response.value.status==202;deadline=time.monotonic()+20;screenshot=False
    while True:
     state=page.request.get(url+'/api/conversations/'+sid).json()
     timing=page.evaluate('window.canaryTiming')
     if timing.get('visible') and not screenshot:
      page.locator('#stream-preview').screenshot(path=str(output/(mode+'-preview.png')));screenshot=True
     if state['status'] not in ('running','stopping','settling','idle'):break
     assert time.monotonic()<deadline;page.wait_for_timeout(30)
    page.wait_for_timeout(200);diagnostics=json.loads((root/'private/diagnostics.json').read_text())
    assert diagnostics['protocol']==('PASS' if mode=='standard' else 'FAIL') and diagnostics['http_attempts']==1
    assert timing.get('visible') and screenshot
    results['cases'][mode]=dict(status=state['status'],diagnostics=diagnostics,browser_submit_to_visible_ms=timing['visible']-timing['submit'],clock='browser performance.now',visible_preview=True)
    # Keep native EventSource open during shutdown, including after failed/HALT case.
    stopped=stop(proc,identity,REPO,root,port,module=MODULE);proc=None
    assert stopped['exit_code']==0
    with socket.socket() as s:assert s.connect_ex(('127.0.0.1',port))!=0
    cleanup=json.loads((root/'private/cleanup.json').read_text());assert cleanup['lease_released'] and cleanup['sdk_streams_closed'] and cleanup['database_consistent'] and not cleanup['cleanup_uncertain']
    results['shutdowns'].append(dict(mode=mode,**stopped,port_released=True,**cleanup));results['shutdowns'][-1]['process_exit_code']=stopped['exit_code'];page.close()
   ctx.close();ctx=None
 finally:
  if ctx is not None:ctx.close()
  if proc is not None and proc.poll() is None:
   stop(proc,identity,REPO,root,port,module=MODULE)
  shutil.rmtree(profile);results['profile_removed']=not profile.exists();(output/'result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 return results

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--chrome',type=Path,required=True);a=p.parse_args();r=run(a.output,a.chrome);print(json.dumps({'cases':list(r['cases']),'real_requests':0,'profile_removed':r['profile_removed']}))
if __name__=='__main__':main()
