"""One loopback bind, passed to Uvicorn without a release/rebind window."""
import json,os,socket
from contextlib import contextmanager
from pathlib import Path
import uvicorn

class OperatorError(RuntimeError):
    def __init__(self,code):self.code=code;super().__init__(code)

def write_status(path,value):
    if path is None:return
    p=Path(path)
    # Files are private diagnostics, not Session/Case events.
    with p.open('w') as f:json.dump(value,f,sort_keys=True)
    p.chmod(0o600)

@contextmanager
def bound_listener(port):
    if type(port) is not int or not 0<=port<=65535:raise OperatorError('port_invalid')
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        # Deliberately never set SO_REUSEPORT.
        try:sock.bind(('127.0.0.1',port));sock.listen(128)
        except OSError as exc:raise OperatorError('port_in_use' if exc.errno in (48,98) else 'bind_failed') from None
        sock.setblocking(False)
        yield sock
    finally:sock.close()

def serve(factory,port,status_file=None):
    """factory is evaluated only after exclusive bind succeeds. No model I/O here."""
    if status_file is not None and Path(status_file).exists():raise OperatorError('status_file_already_exists')
    try:
        with bound_listener(port) as sock:
            actual=sock.getsockname()[1]
            write_status(status_file,dict(state='bound',pid=os.getpid(),port=actual,ready=False,reuseaddr=True,reuseport=False))
            app=factory(actual)
            class OwnedServer(uvicorn.Server):
                shutdown_completed=False
                async def shutdown(self,sockets=None):
                    await super().shutdown(sockets=sockets)
                    self.shutdown_completed=not self.force_exit and not self.lifespan.shutdown_failed and not self.lifespan.error_occurred
                async def startup(self,sockets=None):
                    await super().startup(sockets=sockets)
                    if self.started:
                        write_status(status_file,dict(state='ready',pid=os.getpid(),port=actual,ready=True,reuseaddr=bool(sock.getsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR)),reuseport=False,socket_fd=sock.fileno()))
            server=OwnedServer(uvicorn.Config(app,host='127.0.0.1',port=actual,access_log=False,log_level='warning',timeout_graceful_shutdown=10))
            try:server.run(sockets=[sock])
            except KeyboardInterrupt:
                # Same handling as uvicorn.run, but only after verified graceful shutdown.
                if not server.shutdown_completed:raise
            if not server.shutdown_completed:raise OperatorError('service_shutdown_unconfirmed')
            if not server.started:raise OperatorError('application_not_ready')
            write_status(status_file,dict(state='closed',pid=os.getpid(),port=actual,ready=False,graceful=True))
    except BaseException as exc:
        write_status(status_file,dict(state='failed',ready=False,pid=os.getpid(),error=exc.code if isinstance(exc,OperatorError) else 'service_failed'))
        raise
