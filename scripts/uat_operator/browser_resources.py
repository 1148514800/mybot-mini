"""Close Context while its event loop is alive, then verify own process/profile."""
import os,shlex,shutil,subprocess,tempfile,time
from pathlib import Path
from contextlib import contextmanager
from .ports import OperatorError

ERROR_FIELDS=('primary_error','service_start_error','service_shutdown_error','context_close_error','profile_cleanup_error')

def process_rows(profile):
    rows=[]
    for line in subprocess.check_output(['ps','-axo','pid=,uid=,args='],text=True).splitlines():
        fields=line.strip().split(None,2)
        if len(fields)!=3:continue
        try:args=shlex.split(fields[2])
        except ValueError:continue
        if '--user-data-dir='+str(profile) in args:rows.append(dict(pid=int(fields[0]),uid=int(fields[1]),args=args))
    return rows

def profile_safe(path,parent,identity):
    try:
        return (path.parent==parent and path.resolve()==path and not path.is_symlink() and path.is_dir()
                and (path.stat().st_dev,path.stat().st_ino)==identity and path.stat().st_uid==os.getuid()
                and path.stat().st_mode&0o777==0o700)
    except OSError:return False

@contextmanager
def browser_session(chrome,record,*,factory=None,inspect_processes=process_rows,remove=shutil.rmtree):
    if factory is None:
        from playwright.sync_api import sync_playwright
        factory=sync_playwright
    for field in ERROR_FIELDS:record.setdefault(field,None)
    record.update(context_close_calls=0,browser_process_exit_status='NOT_CHECKED',profile_removed=False,cleanup_uncertain=False)
    parent=Path(tempfile.gettempdir()).resolve();profile=Path(tempfile.mkdtemp(prefix='mybot-v3-browser-',dir=parent));identity=(profile.stat().st_dev,profile.stat().st_ino)
    ctx=None;launch_attempted=False
    try:
        if not profile_safe(profile,parent,identity) or list(profile.iterdir()):raise OperatorError('profile_identity_unproven')
        with factory() as pw:
            try:
                launch_attempted=True
                ctx=pw.chromium.launch_persistent_context(str(profile),executable_path=str(chrome),headless=False,chromium_sandbox=True,viewport={'width':1440,'height':1000})
                rows=inspect_processes(profile)
                main=[r for r in rows if not any(x.startswith('--type=') for x in r['args'])]
                if len(main)!=1 or main[0]['uid']!=os.getuid() or any(x in main[0]['args'] for x in ('--no-sandbox','--disable-web-security','--ignore-certificate-errors')):raise OperatorError('browser_identity_unproven')
                record.update(actual_profile_verified=True,profile_0700_fresh=True,browser_version=ctx.browser.version,headed=True,sandbox=True)
                if ctx.cookies():raise OperatorError('initial_cookie_jar_not_empty')
                record['initial_cookie_jar_empty']=True
                yield ctx
            except BaseException as exc:
                if record['primary_error'] is None:record['primary_error']=exc.code if isinstance(exc,OperatorError) else 'browser_operation_failed'
                raise
            finally:
                if ctx is not None:
                    record['context_close_calls']+=1
                    try:ctx.close()
                    except BaseException:record['context_close_error']='context_close_failed'
        # No Context API can run below this point.
    except BaseException as exc:
        if record['primary_error'] is None:record['primary_error']=exc.code if isinstance(exc,OperatorError) else 'chrome_launch_or_driver_failed'
        raise
    finally:
        try:
            deadline=time.monotonic()+5
            while True:
                rows=inspect_processes(profile)
                if not rows or time.monotonic()>=deadline:break
                time.sleep(.05)
            record['browser_process_exit_status']='EXITED' if not rows else 'STILL_RUNNING'
            safe=not rows and profile_safe(profile,parent,identity) and (ctx is None or record.get('actual_profile_verified') is True)
            # Even launch failure can leave a partial Chrome; only process exit permits removal.
            if not safe:
                record['profile_cleanup_error']='profile_identity_or_process_unproven';record['cleanup_uncertain']=True
            else:
                try:remove(profile);record['profile_removed']=not profile.exists()
                except BaseException:record['profile_cleanup_error']='profile_remove_failed'
                if not record['profile_removed']:record['cleanup_uncertain']=True
        except BaseException:
            record['browser_process_exit_status']='UNKNOWN';record['profile_cleanup_error']='process_inspection_failed';record['cleanup_uncertain']=True
        record['automatic_cleanup_pass']=not any(record[k] for k in ('service_shutdown_error','context_close_error','profile_cleanup_error')) and record['profile_removed'] and record['browser_process_exit_status']=='EXITED'
