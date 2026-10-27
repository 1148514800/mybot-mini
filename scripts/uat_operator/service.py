"""Readiness + listener ownership, graceful cleanup only for captured own child."""
import json,os,signal,subprocess,time
from pathlib import Path
from scripts.local_web_process import _snapshot
from .ports import OperatorError

class OwnedService:
 def __init__(self,arguments,cwd,port,status_file,log_file):
  self.arguments=arguments;self.cwd=Path(cwd).resolve();self.port=port;self.status_file=Path(status_file);self.identity=None;self.ready=False
  with Path(log_file).open('w') as log:self.proc=subprocess.Popen(['uv','run','python',*arguments],cwd=self.cwd,stdout=log,stderr=log)
 def wait_ready(self,timeout=20):
  deadline=time.monotonic()+timeout
  while True:
   state={}
   if self.status_file.exists():
    try:state=json.loads(self.status_file.read_text())
    except ValueError:pass
   if state.get('state')=='failed':raise OperatorError(state.get('error') if state.get('error') in ('port_in_use','bind_failed','application_not_ready') else 'service_start_failed')
   if self.proc.poll() is not None:raise OperatorError('service_start_exit')
   if state.get('ready'):
    pid=state.get('pid')
    snap=_snapshot(pid,self.cwd,self.arguments,self.port)
    if snap['pid']!=self.proc.pid and snap['ppid']!=self.proc.pid:raise OperatorError('listener_not_owned_child')
    self.identity=snap;self.ready=True;return state
   if time.monotonic()>deadline:raise OperatorError('service_ready_timeout')
   time.sleep(.03)
 def close(self,timeout=12):
  began=time.monotonic();direct=False
  # An unready service may still own a child. Never signal an unidentified child.
  if self.proc.poll() is None:self.proc.send_signal(signal.SIGINT)
  try:code=self.proc.wait(1)
  except subprocess.TimeoutExpired:
   if self.identity is not None:
    try:now=_snapshot(self.identity['pid'],self.cwd,self.arguments,self.port)
    except subprocess.CalledProcessError:now=None
    if now is not None:
     if now!=self.identity:raise OperatorError('service_identity_changed')
     if now['pid']!=self.proc.pid:os.kill(now['pid'],signal.SIGINT);direct=True
   try:code=self.proc.wait(timeout)
   except subprocess.TimeoutExpired:raise OperatorError('service_stop_timeout') from None
  # Confirm no listener remains without binding/probing another application's port.
  q=subprocess.run(['lsof','-nP','-iTCP:'+str(self.port),'-sTCP:LISTEN'],capture_output=True,text=True)
  return dict(exit_code=code,seconds=time.monotonic()-began,verified_child_sigint=direct,listener_absent=not bool(q.stdout.strip()),was_ready=self.ready)
