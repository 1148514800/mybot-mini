"""Read-only actual Fixture gates; reuse native Patch policy and original helpers."""
import hashlib,json,os,stat,subprocess,sys
from pathlib import Path
from mybot.tools.patch import ApplyPatchTool,check_metadata
from scripts.uat.check_environment import git
from scripts.uat.fixtures import fingerprint,COMMON
from .fixtures import PROJECTS,ALLOWED
from .oracles import assess


def filesystem_type(root):
    device=subprocess.check_output(['df','-P',str(root)],text=True).splitlines()[-1].split()[0]
    result=subprocess.run(['/usr/sbin/diskutil','info','-plist',device],capture_output=True,check=True)
    import plistlib
    return plistlib.loads(result.stdout).get('FilesystemType')


async def check_environment(case,root):
    requested=Path(root).absolute();root=requested.resolve();before=fingerprint(root)
    report=dict(case=case,mode='OFFLINE',actual_root=str(root),uid=os.getuid(),gid=os.getgid(),
                euid=os.geteuid(),egid=os.getegid(),files=[],directories=[],native_previews=[],issues=[])
    try:
        report['filesystem']=filesystem_type(root)
        if report['filesystem']!='apfs':report['issues'].append('apfs_required')
        if requested.is_symlink():report['issues'].append('symlink_root')
        parent=root.parent.stat();report['root_parent']=dict(uid=parent.st_uid,gid=parent.st_gid,mode=oct(stat.S_IMODE(parent.st_mode)))
        for name in {**COMMON,**PROJECTS[case]}:
            path=root/name;info=path.lstat()
            item=dict(path=name,uid=info.st_uid,gid=info.st_gid,mode=oct(stat.S_IMODE(info.st_mode)),
                      regular=stat.S_ISREG(info.st_mode),symlink=path.is_symlink(),
                      version=[info.st_dev,info.st_ino,info.st_mtime_ns,info.st_ctime_ns])
            report['files'].append(item)
            if not item['regular']:report['issues'].append('not_regular_file');continue
            parent=path.parent
            while True:
                pi=parent.lstat()
                if not stat.S_ISDIR(pi.st_mode):report['issues'].append('unsafe_parent')
                report['directories'].append(dict(path=parent.relative_to(root).as_posix(),uid=pi.st_uid,gid=pi.st_gid,mode=oct(stat.S_IMODE(pi.st_mode))))
                if parent==root:break
                parent=parent.parent
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            try:
                check_metadata(fd,os.fstat(fd));item['native_acl_xattr_mode_supported']=True
                item['xattr_present']=bool(subprocess.check_output(['xattr',str(path)])) if sys.platform=='darwin' else bool(os.listxattr(path))
                item['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError,ValueError):
                item['native_acl_xattr_mode_supported']=False;report['issues'].append('unsupported_metadata')
            finally:os.close(fd)
        tool=ApplyPatchTool(root,patch_mode='preview')
        for name in ALLOWED[case]:
            path=root/name
            if path.is_symlink() or not path.is_file():report['issues'].append('unsafe_preview_target');continue
            data=path.read_bytes();text=data.decode()
            result=await tool.execute(dry_run=True,changes=[dict(op='update',path=name,expected_sha256=hashlib.sha256(data).hexdigest(),
                        edits=[dict(old_text=text,new_text=text+'\n# preflight preview only\n')])])
            report['native_previews'].append(dict(path=name,passed=result.success,code=result.metadata.get('safe_error_code')))
            if not result.success:report['issues'].append(result.metadata.get('safe_error_code') or 'preview_failed')
        report['git_head']=git(root,'rev-parse','HEAD');report['git_index_sha256']=hashlib.sha256(git(root,'ls-files','--stage').encode()).hexdigest()
        report['git_status']=git(root,'status','--porcelain')
        if report['git_status']:report['issues'].append('dirty_fixture')
        if case!='T03':
            public=await assess(case,root,hidden=False);hidden=await assess(case,root)
            report.update(public_tests=public,independent_tests=hidden)
            expected=all((root/k).read_text()==v for k,v in PROJECTS[case].items())
            report['initial_bug_confirmed']=bool(expected and public['sandbox_applied'] and hidden['sandbox_applied'] and
                public['status']=='completed' and hidden['status']=='completed' and public['returncode']==1 and
                'FAIL:' in public['stderr'] and hidden['returncode']!=0 and 'AssertionError' in hidden['stderr'])
            if not report['initial_bug_confirmed']:report['issues'].append('initial_bug_or_test_entry_not_confirmed')
    except (OSError,ValueError,subprocess.SubprocessError,RuntimeError):report['issues'].append('environment_probe_failed')
    report['directories']=list({x['path']:x for x in report['directories']}.values())
    report['unchanged']=before==fingerprint(root)
    if not report['unchanged']:report['issues'].append('preflight_mutated_fixture')
    report['status']='PASS' if not report['issues'] else 'BLOCKED'
    return report


async def require_environment(case,root):
    report=await check_environment(case,root)
    if report['status']!='PASS':raise RuntimeError('v2_fixture_blocked')
    return report
