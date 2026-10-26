"""Non-production same-origin cookie/localStorage isolation. Optional Playwright.

Run with an external uv --no-project --with playwright environment. No user or
MyBot page/config is opened. Profiles are always fresh and cleaned by finally.
"""
import argparse,json,os,subprocess,tempfile,threading,shutil,hashlib
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler

HTML='''<!doctype html><meta charset="utf-8"><title>Source-aware UAT isolation probe</title><h1>Non-production browser isolation</h1><p>Only synthetic markers; no MyBot authentication or provider.</p><input aria-label="Probe input"><button id="a" onclick="document.cookie='source_probe_a=synthetic_a; SameSite=Strict; path=/';localStorage.setItem('source_probe_a','synthetic_a');show()">Write A</button><button id="b" onclick="document.cookie='source_probe_b=synthetic_b; SameSite=Strict; path=/';localStorage.setItem('source_probe_b','synthetic_b');show()">Write B</button><pre id="state"></pre><script>function read(){return {cookieA:document.cookie.includes('source_probe_a='),cookieB:document.cookie.includes('source_probe_b='),storageA:localStorage.getItem('source_probe_a')!==null,storageB:localStorage.getItem('source_probe_b')!==null}}function show(){document.getElementById('state').textContent=JSON.stringify(read())}show()</script>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*a):pass

def run(chrome,output):
    from playwright.sync_api import sync_playwright
    os.umask(0o077);output=Path(output).absolute();output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if output.exists() or output.parent.is_symlink() or output.parent.stat().st_mode&0o077:raise RuntimeError('private new output required')
    root=Path(tempfile.mkdtemp(prefix='source-aware-isolation-')).resolve();server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();contexts=[];profiles=[];result={'passed':False,'profiles_removed':False,'server_closed':False}
    try:
        with sync_playwright() as pw:
            pages=[];info=[]
            for label in ['A','B']:
                profile=Path(tempfile.mkdtemp(prefix='profile-'+label+'-',dir=root));profiles.append(profile)
                assert profile.resolve()==profile and not profile.is_symlink() and not list(profile.iterdir()) and profile.stat().st_mode&0o777==0o700
                context=pw.chromium.launch_persistent_context(str(profile),executable_path=str(chrome),headless=False,chromium_sandbox=True,viewport={'width':1100,'height':700});contexts.append(context);assert not context.cookies()
                matches=[line for line in subprocess.check_output(['ps','-axo','pid=,uid=,command='],text=True).splitlines() if '--user-data-dir='+str(profile) in line and '--type=' not in line]
                assert len(matches)==1 and int(matches[0].split()[1])==os.geteuid() and not any(v in matches[0] for v in ['--no-sandbox','--disable-web-security','--ignore-certificate-errors'])
                info.append(dict(label=label,pid=int(matches[0].split()[0]),uid=os.geteuid(),new_0700_non_symlink=True,launch_user_data_dir_verified=True,profile_path_sha256=hashlib.sha256(str(profile).encode()).hexdigest()))
                page=context.new_page();page.goto('http://127.0.0.1:'+str(server.server_port));page.get_by_label('Probe input').fill('Synthetic input '+label);assert page.get_by_label('Probe input').input_value()=='Synthetic input '+label;pages.append(page)
            read=lambda page:page.evaluate('read()')
            initial=[read(p) for p in pages];assert all(not any(x.values()) for x in initial)
            pages[0].locator('#a').click();a=read(pages[0]);b0=read(pages[1]);assert a==dict(cookieA=True,cookieB=False,storageA=True,storageB=False) and not any(b0.values())
            pages[1].locator('#b').click();b=read(pages[1]);a2=read(pages[0]);assert b==dict(cookieA=False,cookieB=True,storageA=False,storageB=True) and a2==a
            for label,page in zip(['A','B'],pages):page.screenshot(path=str(output.parent/('probe-'+label+'.png')))
            result.update(passed=True,browser_version=contexts[0].browser.version,headed=True,chromium_sandbox=True,playwright_version=__import__('importlib.metadata',fromlist=['version']).version('playwright'),initial=initial,profile_A=a2,profile_B=b,profiles=info,same_origin=True,click_input_dom_screenshot_verified=True,mybot_or_provider_accessed=False)
            for context in contexts:context.close()
            contexts=[]
    finally:
        for context in contexts:context.close()
        server.shutdown();server.server_close();thread.join(timeout=5);result['server_closed']=not thread.is_alive();shutil.rmtree(root);result['profiles_removed']=not root.exists()
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');output.chmod(0o600)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--chrome',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.chrome,a.output);print(json.dumps(dict(passed=r['passed'],version=r.get('browser_version'),profiles_removed=r['profiles_removed'],server_closed=r['server_closed'])))
if __name__=='__main__':main()
