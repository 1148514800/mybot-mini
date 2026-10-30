"""Read-only project preflight using the explicit shared configuration contract."""
import asyncio
from dataclasses import replace
import os
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / 'config/config.json'


from ..config import ConfigError as LaunchError, read_config, check_providers, config_from_document


def normalize_workspace(value, *, explicit=False):
    try:
        if not isinstance(value, (str,Path)) or not str(value).strip() or any(ord(c)<32 for c in str(value)):
            raise LaunchError('WORKSPACE_INVALID')
        path = Path(value).expanduser()
        if explicit and not path.is_absolute(): raise LaunchError('WORKSPACE_NOT_ABSOLUTE')
        path = path.resolve(strict=True)
        if not path.is_dir(): raise LaunchError('WORKSPACE_NOT_DIRECTORY')
        if not os.access(path, os.R_OK | os.X_OK): raise LaunchError('WORKSPACE_INACCESSIBLE')
        with os.scandir(path): pass
        return path
    except FileNotFoundError: raise LaunchError('WORKSPACE_NOT_FOUND') from None
    except (PermissionError,OSError,RuntimeError,ValueError): raise LaunchError('WORKSPACE_INACCESSIBLE') from None


async def inspect_project(path):
    from ..tools.readonly_process import run_readonly, GIT_OPTIONS
    async def git(*args, allowed=(0,)):
        try:
            result = await run_readonly('git', [*GIT_OPTIONS,*args], cwd=path, workspace=path, stdout_limit=8192)
        except (OSError, ValueError): raise LaunchError('GIT_UNAVAILABLE') from None
        if result.timed_out or result.truncated: raise LaunchError('GIT_CHECK_INCOMPLETE')
        if result.code not in allowed: raise LaunchError('GIT_REPOSITORY_INVALID')
        return result
    # Do not discover a parent repository for an arbitrary subdirectory.
    if not (path/'.git').exists(): raise LaunchError('GIT_ROOT_REQUIRED')
    root = (await git('rev-parse','--show-toplevel')).stdout.decode('utf-8').strip()
    if Path(root).resolve() != path: raise LaunchError('GIT_ROOT_REQUIRED')
    if (await git('rev-parse','--is-inside-work-tree')).stdout.strip() != b'true':
        raise LaunchError('GIT_WORKTREE_REQUIRED')
    branch = await git('symbolic-ref','--quiet','--short','HEAD', allowed=(0,1))
    head = await git('rev-parse','--verify','HEAD^{commit}', allowed=(0,128))
    if head.code and branch.code: raise LaunchError('GIT_REPOSITORY_INVALID')
    # Reuse native filter suppression: even status must not execute repository filters.
    from ..tools.git_tools import GitStatusTool
    status = await GitStatusTool(path).git(['status','--porcelain=v1','--untracked-files=no','--ignore-submodules=all'], path, stdout_limit=2*1024*1024)
    if status.code or status.timed_out or status.truncated: raise LaunchError('GIT_INDEX_INVALID')
    name = branch.stdout.decode('utf-8').strip() if not branch.code else 'detached HEAD'
    return dict(name=path.name, branch=name[:256], detached=branch.code==1, unborn=head.code!=0)


def redact_report(value, document):
    llm = document.get('llm',{}); providers = llm.get('providers',{})
    secrets = [p.get('api_key') for p in providers.values() if isinstance(p,dict)] + [llm.get('api_key')]
    def clean(item):
        if isinstance(item,str):
            for secret in secrets:
                if isinstance(secret,str) and secret: item=item.replace(secret,'[REDACTED]')
            return item
        if isinstance(item,dict): return {k:clean(v) for k,v in item.items()}
        if isinstance(item,list): return [clean(v) for v in item]
        return item
    return clean(value)


def prepare_launch(workspace=None, *, config_path=None, config_factory=None):
    document = read_config(DEFAULT_CONFIG if config_path is None else config_path)
    try:
        config = config_from_document(document)
        if config_factory is not None:
            config = config_factory()
        path = normalize_workspace(workspace if workspace is not None else config.workspace, explicit=workspace is not None)
        config = replace(config, workspace=path)
    except LaunchError: raise
    except (ValueError,TypeError,RuntimeError): raise LaunchError('CONFIG_VALIDATION_FAILED') from None
    try: project = asyncio.run(inspect_project(path))
    except (OSError,UnicodeError,ValueError): raise LaunchError('GIT_METADATA_INVALID') from None
    # Runtime persistence must never create files inside the selected project.
    if config.storage_backend=='event_sqlite' and config.session_event_path.resolve().is_relative_to(path):
        raise LaunchError('STORAGE_INSIDE_WORKSPACE')
    from ..config import provider_order
    order = provider_order(document['llm']['provider'], document['llm']['providers'])
    report = dict(ok=True, workspace=str(path), project=project, default_provider=document['llm']['provider'],
        provider_order=order, provider_fields='valid', provider_connection_tested=False, coding=config.coding_enabled, patch_mode=config.coding_patch_mode,
        preview_receipt=config.coding_preview_receipt, file_access="read_only",
        run_command=config.coding_command['mode'], command_requires_approval=config.coding_command['mode']!='off',
        git='valid', check_only_no_requests=True)
    return config, redact_report(project,document), redact_report(report,document)
