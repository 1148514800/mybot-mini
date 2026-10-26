"""Operator-only verified local fixture process cleanup, never a model tool.

uv may not forward a programmatic SIGINT with inherited terminal input. Capture
our exact serving child while it owns the port; reverify immediately before an
additional graceful SIGINT. Never scan-and-kill, force-kill or remove a lock.
"""
import os,signal,subprocess,time,shlex
from pathlib import Path


def _snapshot(pid,cwd,arguments,port):
 row=subprocess.check_output(['ps','-p',str(pid),'-o','uid=,ppid=,lstart='],text=True).strip()
 uid,ppid,started=row.split(None,2)
 if int(uid)!=os.getuid():raise RuntimeError('fixture_process_uid_changed')
 args=shlex.split(subprocess.check_output(['ps','-p',str(pid),'-o','args='],text=True))
 if args[1:]!=arguments or Path(args[0]).name.lower() not in ('python','python3','python3.12'):
  raise RuntimeError('fixture_process_command_changed')
 locations=subprocess.check_output(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],text=True).splitlines()
 if not any(x.startswith('n') and Path(x[1:]).resolve()==cwd.resolve() for x in locations):raise RuntimeError('fixture_process_cwd_changed')
 listener=subprocess.check_output(['lsof','-nP','-a','-p',str(pid),'-iTCP:'+str(port),'-sTCP:LISTEN'],text=True)
 if '127.0.0.1:'+str(port) not in listener:raise RuntimeError('fixture_listener_changed')
 return dict(pid=pid,uid=int(uid),ppid=int(ppid),started=started,args=args)


def capture(launcher,cwd,module,root,port):
 arguments=['-m',module,'--root',str(root),'--port',str(port)]
 rows=subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines()
 candidates=[int(p) for p,parent in (line.split() for line in rows) if int(parent)==launcher.pid]
 candidates.append(launcher.pid)
 for pid in candidates:
  try:return _snapshot(pid,cwd,arguments,port)
  except (subprocess.CalledProcessError,RuntimeError):continue
 raise RuntimeError('owned_fixture_child_identity_unproven')


def stop(launcher,identity,cwd,root,port,module='scripts.stream_protocol_server',timeout=10):
 began=time.monotonic();direct=False
 if launcher.poll() is None:launcher.send_signal(signal.SIGINT)
 try:code=launcher.wait(1)
 except subprocess.TimeoutExpired:
  # Reverify everything, including birth time: a stale PID is never authority.
  try:now=_snapshot(identity['pid'],cwd,['-m',module,'--root',str(root),'--port',str(port)],port)
  except subprocess.CalledProcessError:
   # Listener/child already gone: shutdown may be draining. Wait, do not signal.
   code=launcher.wait(timeout)
  else:
   if now!=identity:raise RuntimeError('fixture_child_identity_changed')
   if identity['pid']!=launcher.pid:
    os.kill(identity['pid'],signal.SIGINT);direct=True
   code=launcher.wait(timeout)
 return dict(exit_code=code,seconds=time.monotonic()-began,verified_child_sigint=direct)
