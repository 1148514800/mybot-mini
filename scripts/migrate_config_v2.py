"""Explicit, backed-up migration; credentials and configuration bodies are never printed."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import stat
import tempfile

from mybot.config import read_config, config_from_document, ConfigError


def migrate(config, *, apply=False, confirm_token_estimate=False):
    path = Path(config).absolute()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ConfigError('CONFIG_FILE_UNSAFE')
    original = path.read_bytes()
    document = read_config(path)
    result = deepcopy(document)
    changes = []
    for section in ('coding', 'session', 'context'):
        if type(result.get(section, {})) is not dict:
            raise ConfigError('CONFIG_SECTION_INVALID')
    coding = result.get('coding', {})
    if 'file_access' in coding:
        if coding['file_access'] not in ('read_only', 'legacy_confirm'):
            raise ConfigError('CONFIG_FILE_ACCESS_INVALID')
        if coding['file_access'] == 'legacy_confirm' and coding.get('patch_mode', 'off') != 'off':
            raise ConfigError('LEGACY_PERMISSION_CONFLICT')
        changes.append('coding.file_access: retired; ordinary file access is read_only')
        del coding['file_access']
    session = result.get('session', {})
    if session.get('persist', False) is not False or session.get('backend') == 'legacy_json':
        raise ConfigError('SESSION_DATA_MIGRATION_REQUIRED_NO_AUTOMATIC_BACKEND_CHANGE')
    for field in ('persist', 'path'):
        if field in session:
            del session[field]; changes.append('session.' + field + ': retired inactive JSON setting')
    budget = result.get('context', {}).get('token_budget', {})
    if isinstance(budget, dict) and budget.get('mode') == 'legacy_chars':
        if not confirm_token_estimate:
            raise ConfigError('TOKEN_ESTIMATE_CONFIRMATION_REQUIRED_INPUT_LIMIT_UNCHANGED')
        budget['mode'] = 'estimate'
        changes.append('legacy_chars -> estimate: UTF-8 estimate, NOT equivalent; input_limit unchanged')
    # No writes (including backups) before the full new contract validates.
    config_from_document(result)
    encoded = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
    if json.loads(encoded) != result:
        raise ConfigError('MIGRATION_VERIFICATION_FAILED')
    if path.read_bytes() != original:
        raise ConfigError('CONFIG_CHANGED')
    if apply and changes:
        backup = path.with_name(path.name + '.v1-backup')
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(original); stream.flush(); os.fsync(stream.fileno())
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.config-v2-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
                config_from_document(read_config(temporary))
                if path.read_bytes() != original:
                    raise ConfigError('CONFIG_CHANGED')
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    return dict(ok=True, applied=bool(apply and changes), changes=changes, backup_created=bool(apply and changes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    mode = parser.add_mutually_exclusive_group(); mode.add_argument('--dry-run', action='store_true'); mode.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-token-estimate', action='store_true')
    args = vars(parser.parse_args()); args.pop('dry_run')
    try: result = migrate(**args)
    except ConfigError as exc: result = exc.result
    except Exception: result = dict(ok=False, error_type='CONFIG_MIGRATION_FAILED_ORIGINAL_PRESERVED')
    print(json.dumps(result)); return 0 if result['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
