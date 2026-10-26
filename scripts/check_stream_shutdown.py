"""Real local Uvicorn + uv launcher, disposable state, no model network."""
import asyncio,json,os,signal,socket,sqlite3,subprocess,tempfile,time,unittest
from pathlib import Path
import httpx
from mybot.web.runtime import ChatRuntime
from mybot.web.server import create_app
from scripts.eventstore_fixtures import configuration
from scripts.streaming_fixtures import Client,Stream,chunk
from mybot.workspace_lease import WorkspaceLease

REPO=Path(__file__).resolve().parents[1]
class ProcessChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='stream-shutdown-');self.root=Path(self.tmp.name).resolve();os.chmod(self.root,0o700)
  with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
  self.url='http://127.0.0.1:'+str(self.port);self.log=(self.root/'log').open('w')
  self.proc=subprocess.Popen(['uv','run','python','-m','scripts.stream_protocol_server','--root',str(self.root),'--port',str(self.port)],cwd=REPO,stdout=self.log,stderr=self.log)
  self.client=httpx.Client(base_url=self.url,trust_env=False,timeout=5);self.active=None;self.addCleanup(self.cleanup)
  deadline=time.monotonic()+15
  while True:
   try:
    if self.client.get('/').status_code==200:break
   except httpx.TransportError:pass
   if self.proc.poll() is not None:raise AssertionError('server startup failed')
   if time.monotonic()>deadline:raise AssertionError('startup timeout')
   time.sleep(.05)
  self.csrf=self.client.get('/api/bootstrap').json()['csrf'];self.headers={'Origin':self.url,'X-Mybot-CSRF':self.csrf};self.sid=self.client.post('/api/conversations',headers=self.headers,json={}).json()['id']
 def cleanup(self):
  if self.active:self.active.close()
  self.client.close()
  if self.proc.poll() is None:
   self.proc.send_signal(signal.SIGINT);self.proc.wait(12)
  self.log.close();self.tmp.cleanup()
 def sse(self,last=0):
  cm=self.client.stream('GET','/api/conversations/'+self.sid+'/events',headers={'Last-Event-ID':str(last)});r=cm.__enter__();self.active=r;return cm,r,r.iter_lines()
 def shutdown(self):
  started=time.monotonic();self.proc.send_signal(signal.SIGINT);code=self.proc.wait(12);elapsed=time.monotonic()-started
  self.assertEqual(code,0);self.assertLess(elapsed,8)
  with socket.socket() as s:self.assertNotEqual(s.connect_ex(('127.0.0.1',self.port)),0)
  lease=WorkspaceLease(self.root/'workspace').acquire();lease.release()
  self.log.flush();self.assertNotIn('timeout graceful shutdown exceeded',(self.root/'log').read_text())
 def test_no_browser_sigint_launcher(self):self.shutdown()
 def test_open_sse_shutdown(self):
  cm,r,lines=self.sse();self.shutdown();r.close();cm.__exit__(None,None,None)
 def test_inflight_stream_shutdown(self):
  self.assertEqual(self.client.post('/api/conversations/'+self.sid+'/messages',json={'message':'合成C关闭'},headers=self.headers).status_code,202)
  time.sleep(.35);cm,r,lines=self.sse();self.shutdown();r.close();cm.__exit__(None,None,None)
  with sqlite3.connect(self.root/'private/events.sqlite3') as db:
   self.assertEqual(db.execute('select state from turns').fetchone()[0],'cancelled');self.assertEqual(db.execute("select count(*) from messages where role='assistant'").fetchone()[0],0)
  self.assertTrue((self.root/'stream-closes.jsonl').exists())
 def test_halt_does_not_block_shutdown(self):
  self.client.post('/api/conversations/'+self.sid+'/messages',json={'message':'合成F错误'},headers=self.headers)
  deadline=time.monotonic()+8
  while not (self.root/'synthetic-ledger.sqlite').exists() or time.monotonic()<deadline:
   with sqlite3.connect(self.root/'synthetic-ledger.sqlite') as db:halt=db.execute("select value from meta where key='halt'").fetchone()
   if halt:break
   self.assertLess(time.monotonic(),deadline);time.sleep(.05)
  count=len((self.root/'sdk-requests.jsonl').read_text().splitlines())
  self.assertEqual(self.client.post('/api/conversations/'+self.sid+'/messages',json={'message':'合成A禁止新请求'},headers=self.headers).status_code,409)
  self.assertEqual(len((self.root/'sdk-requests.jsonl').read_text().splitlines()),count)
  cm,r,lines=self.sse();self.shutdown();r.close();cm.__exit__(None,None,None)
  with sqlite3.connect(self.root/'synthetic-ledger.sqlite') as db:self.assertEqual(db.execute("select value from meta where key='halt'").fetchone()[0],'synthetic_protocol_failure')
 def test_sse_finite_and_resume_no_duplicates(self):
  self.client.post('/api/conversations/'+self.sid+'/messages',json={'message':'合成A'},headers=self.headers)
  time.sleep(1.1)
  cm,r,lines=self.sse();ids=[int(v[4:]) for v in lines if v.startswith('id: ')];r.close();cm.__exit__(None,None,None);self.assertTrue(ids)
  cm,r,lines=self.sse(max(ids));rest=list(lines);r.close();cm.__exit__(None,None,None)
  self.assertFalse(any(v.startswith('id: ') for v in rest));self.assertEqual(len((self.root/'sdk-requests.jsonl').read_text().splitlines()),1)

 def test_verified_operator_process_stop(self):
  from scripts.local_web_process import capture,stop
  identity=capture(self.proc,REPO,'scripts.stream_protocol_server',self.root,self.port)
  self.assertEqual(identity['uid'],os.getuid());cm,r,lines=self.sse()
  result=stop(self.proc,identity,REPO,self.root,self.port);self.assertEqual(result['exit_code'],0);r.close();cm.__exit__(None,None,None)

class RuntimeChecks(unittest.IsolatedAsyncioTestCase):
 async def test_shutdown_not_routed_through_admission_override(self):
  with tempfile.TemporaryDirectory() as t:
   r=ChatRuntime(configuration(Path(t).resolve()),client_factory=lambda _:Client([]))
   async def denied(c):raise RuntimeError('HALT')
   r.stop=denied
   r.new();await r.close();self.assertTrue(r.closed)
 async def test_client_close_timeout_retains_uncertain(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as t:
   class Bad(Client):
    async def close(self):raise TimeoutError('synthetic close timeout')
   client=Bad([Stream([chunk('ok',finish='stop')])]);r=ChatRuntime(configuration(Path(t).resolve(),web_streaming=True),client_factory=lambda _:client);c=r.new();await r.start(c,'synthetic');await c.task
   self.assertTrue(r.cleanup_uncertain);self.assertEqual(c.status,'cleanup_uncertain');await r.close()

 async def test_manager_exit_stays_in_entering_task(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as t:
   seen=[]
   class Manager:
    def __init__(self,*args,**kwargs):pass
    async def __aenter__(self):self.task=asyncio.current_task();return self
    async def __aexit__(self,*args):
     seen.append(self.task is asyncio.current_task())
     if not seen[-1]:raise RuntimeError('wrong cleanup task')
   client=Client([Stream([chunk('ok',finish='stop')])])
   with patch('mybot.web.runtime.MCPClientManager',Manager):
    r=ChatRuntime(configuration(Path(t).resolve(),web_streaming=True),client_factory=lambda _:client);c=r.new();await r.start(c,'synthetic');await c.task
    self.assertEqual(seen,[True]);self.assertFalse(r.cleanup_uncertain);await r.close()
 async def test_cooperative_client_cleanup_is_bounded(self):
  with tempfile.TemporaryDirectory() as t:
   class Slow(Client):
    async def close(self):await asyncio.sleep(60)
   client=Slow([Stream([chunk('ok',finish='stop')])]);r=ChatRuntime(configuration(Path(t).resolve(),web_streaming=True),client_factory=lambda _:client);c=r.new()
   await r.start(c,'synthetic');started=asyncio.get_running_loop().time();await c.task
   self.assertLess(asyncio.get_running_loop().time()-started,5);self.assertTrue(r.cleanup_uncertain);await r.close()

 async def test_changed_process_identity_never_signalled(self):
  from unittest.mock import patch,Mock
  from scripts.local_web_process import stop
  launcher=Mock(pid=101);launcher.poll.return_value=None;launcher.wait.side_effect=subprocess.TimeoutExpired('own',1)
  with patch('scripts.local_web_process._snapshot',return_value={'pid':202,'started':'different'}),patch('scripts.local_web_process.os.kill') as kill:
   with self.assertRaises(RuntimeError):stop(launcher,{'pid':202,'started':'original'},Path('/tmp'),Path('/tmp/fixture'),1234)
   kill.assert_not_called()

def check_stream_shutdown():
 suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (ProcessChecks,RuntimeChecks)])
 r=unittest.TextTestRunner(verbosity=2).run(suite)
 if not r.wasSuccessful():raise AssertionError('shutdown checks failed')
if __name__=='__main__':check_stream_shutdown()
