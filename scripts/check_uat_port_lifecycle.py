"""Native macOS/Uvicorn lifecycle evidence, no model requests."""
import json,os,pathlib,socket,subprocess,tempfile,time,unittest
from contextlib import closing
import httpx
from scripts.uat_operator.ports import bound_listener,serve,OperatorError
from scripts.uat_operator.service import OwnedService
ROOT=pathlib.Path(__file__).resolve().parents[1]

class PortChecks(unittest.TestCase):
 def test_loopback_options(self):
  with bound_listener(0) as s:
   self.assertEqual(s.getsockname()[0],'127.0.0.1');self.assertNotEqual(s.getsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR),0)
   self.assertEqual(s.getsockopt(socket.SOL_SOCKET,socket.SO_REUSEPORT),0)
 def test_external_listener_blocks_before_factory(self):
  called=[]
  with bound_listener(0) as s:
   with self.assertRaisesRegex(OperatorError,'port_in_use'):serve(lambda _:called.append(1),s.getsockname()[1])
  self.assertFalse(called)
 def test_owned_listener_also_blocks(self):
  with bound_listener(0) as s:
   with self.assertRaises(OperatorError):
    with bound_listener(s.getsockname()[1]):pass
 def test_connect_failure_not_bind_authority(self):
  with socket.socket() as s:
   s.bind(('127.0.0.1',0));port=s.getsockname()[1]
   with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0)
   with self.assertRaises(OperatorError):
    with bound_listener(port):pass
 def test_same_socket_not_released_for_uvicorn(self):
  with bound_listener(0) as s:
   fd=s.fileno()
   with self.assertRaises(OperatorError):
    with bound_listener(s.getsockname()[1]):pass
   self.assertEqual(s.fileno(),fd)
 def test_invalid_port(self):
  with self.assertRaises(OperatorError):
   with bound_listener(True):pass
 def test_thirty_native_restarts_with_sse_keepalive(self):
  evidence=[]
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp).resolve()
   with bound_listener(0) as s:port=s.getsockname()[1]
   for i in range(30):
    status=root/f'{i}-status.json';fixture=root/f'round-{i}'
    args=['-m','scripts.uat_operator.lifecycle_fixture','--root',str(fixture),'--port',str(port),'--status-file',str(status),'--ready-delay','.12' if i==0 else '0']
    service=OwnedService(args,ROOT,port,status,root/f'{i}.log');client=None;stream=None
    try:
     ready=service.wait_ready();self.assertTrue(ready['reuseaddr']);self.assertFalse(ready['reuseport']);self.assertEqual(ready['pid'],service.identity['pid'])
     client=httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=8);self.assertEqual(client.get('/').status_code,200)
     boot=client.get('/api/bootstrap').json();headers={'Origin':f'http://127.0.0.1:{port}','X-Mybot-CSRF':boot['csrf']}
     sid=client.post('/api/conversations',json={},headers=headers).json()['id']
     if i%3==0:
      stream=client.stream('GET','/api/conversations/'+sid+'/events');stream.__enter__()
     closed=service.close();self.assertEqual(closed['exit_code'],0);self.assertTrue(closed['listener_absent'])
     cleanup=json.loads((fixture/'cleanup.json').read_text());self.assertTrue(cleanup['lease_released']);self.assertTrue(cleanup['runtime_closed'])
     with bound_listener(port) as acquired:self.assertEqual(acquired.getsockname()[1],port)
     evidence.append(dict(round=i+1,pid=ready['pid'],listener_pid=service.identity['pid'],reuseaddr=True,reuseport=False,ready=True,exit_code=closed['exit_code'],sse=i%3==0,keepalive=True,port_reacquired=True,lease_released=True,real_requests=0))
    finally:
     if stream:stream.__exit__(None,None,None)
     if client:client.close()
     if service.proc.poll() is None:service.close()
  target=os.environ.get('MYBOT_V3_PORT_EVIDENCE')
  if target:pathlib.Path(target).write_text(json.dumps(dict(rounds=evidence,passed=len(evidence)==30,original_t02_root_cause='UNKNOWN'),indent=2))
if __name__=='__main__':unittest.main()

class AdditionalPortChecks(unittest.TestCase):
 def test_active_close_timewait_plain_bind_difference(self):
  with bound_listener(0) as listener:
   port=listener.getsockname()[1];listener.settimeout(2)
   client=socket.create_connection(('127.0.0.1',port));accepted,_=listener.accept()
   accepted.sendall(b'x');self.assertEqual(client.recv(1),b'x');accepted.shutdown(socket.SHUT_WR);accepted.close();self.assertEqual(client.recv(1),b'');client.close()
  with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0)
  with socket.socket() as plain:
   with self.assertRaises(OSError):plain.bind(('127.0.0.1',port))
  with bound_listener(port) as recovered:self.assertEqual(recovered.getsockname()[1],port)
 def test_application_bound_but_not_ready(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t).resolve();status=root/'status.json'
   with bound_listener(0) as s:port=s.getsockname()[1]
   args=['-m','scripts.uat_operator.lifecycle_fixture','--root',str(root/'fixture'),'--port',str(port),'--status-file',str(status),'--ready-delay','1']
   service=OwnedService(args,ROOT,port,status,root/'server.log')
   try:
    deadline=time.monotonic()+10
    while not status.exists() and time.monotonic()<deadline:time.sleep(.01)
    state=json.loads(status.read_text());self.assertEqual(state['state'],'bound');self.assertFalse(state['ready'])
    self.assertFalse(service.ready);service.wait_ready();self.assertTrue(service.ready)
   finally:self.assertEqual(service.close()['exit_code'],0)
 def test_conflicting_server_does_not_construct_attempt(self):
  with tempfile.TemporaryDirectory() as t,bound_listener(0) as occupied:
   root=pathlib.Path(t).resolve();port=occupied.getsockname()[1];batch=root/'never-created';status=root/'status.json'
   args=['-m','scripts.streaming_steer_recovery_v3.mock','--root',str(batch),'--port',str(port),'--case','N01','--status-file',str(status)]
   service=OwnedService(args,ROOT,port,status,root/'server.log')
   with self.assertRaises(OperatorError):service.wait_ready()
   closed=service.close();self.assertNotEqual(closed['exit_code'],0);self.assertFalse(batch.exists());self.assertEqual(json.loads(status.read_text())['error'],'port_in_use')
 def test_stop_timeout_is_not_success(self):
  from unittest.mock import Mock
  service=OwnedService.__new__(OwnedService);service.identity=None;service.proc=Mock();service.proc.poll.return_value=None;service.proc.wait.side_effect=subprocess.TimeoutExpired('own',1)
  with self.assertRaisesRegex(OperatorError,'service_stop_timeout'):service.close(timeout=.01)
  service.proc.send_signal.assert_called_once()
