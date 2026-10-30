"""One-time JSON reader; never installs an executable legacy runtime backend."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from mybot.config import read_config, ConfigError, GatewayConfig
from mybot.storage.session_store import validate_turns
from mybot.storage.event_privacy import safe_text
from mybot.storage.history import open_store, SessionHistory


class MigrationError(ValueError):
    pass


def migrate(source, destination, *, workspace, apply=False, flatten_tool_history=False, confirm_lossy=False, channel='cli'):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 16 * 1024 * 1024:
        raise MigrationError('SOURCE_UNSAFE_OR_TOO_LARGE')
    original = source.read_bytes()
    try:
        document = read_config(source)
        if set(document) != {'version', 'turns'} or type(document['version']) is not int or document['version'] != 1:
            raise ValueError()
        validate_turns(document['turns'])
    except (ValueError, ConfigError):
        raise MigrationError('INVALID_LEGACY_SESSION') from None
    turns = document['turns']
    tool_count = sum(len(m.get('tool_calls') or []) for turn in turns for m in turn)
    if tool_count and not flatten_tool_history:
        raise MigrationError('UNSUPPORTED_TOOL_HISTORY')
    if flatten_tool_history and not confirm_lossy:
        raise MigrationError('LOSSY_CONFIRMATION_REQUIRED')
    projected = []
    for turn in turns:
        assistant = [m['content'] for m in turn[1:] if m['role'] == 'assistant' and m.get('content') is not None]
        reply = '\n[迁移：中间工具交互已省略]\n'.join(assistant)
        projected.append([dict(role='user', content=turn[0]['content']), dict(role='assistant', content=reply)])
    if any(safe_text(m['content'])[0] != m['content'] for turn in projected for m in turn):
        raise MigrationError('TEXT_NOT_LOSSLESSLY_REPRESENTABLE')
    workspace = Path(workspace).resolve(strict=True)
    if destination.is_relative_to(workspace) or destination.resolve().is_relative_to(workspace):
        raise MigrationError('STORAGE_INSIDE_WORKSPACE')
    # Never open an existing destination, including its SQLite journal/sidecars.
    if destination.exists() or destination.is_symlink() or any(Path(str(destination) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise MigrationError('DESTINATION_EXISTS')
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink() or parent.resolve() != parent or parent.stat().st_uid != os.geteuid() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise MigrationError('DESTINATION_DIRECTORY_NOT_PRIVATE')
    # Dry-run is read-only: the candidate database is in an independent temporary directory.
    with tempfile.TemporaryDirectory(prefix='mybot-session-migration-') as temp:
        candidate = Path(temp).resolve() / 'events.sqlite3'
        config = GatewayConfig(workspace=workspace, session_backend='event_sqlite', session_event_path=candidate)
        store = open_store(config, channel)
        try:
            history = SessionHistory(store)
            for user, assistant in projected:
                history.start(user['content'])
                history.finish(assistant['content'])
            rows = store.query('SELECT role,content FROM messages WHERE session_id=? ORDER BY sequence', (history.sid,))
            expected = [m for turn in projected for m in turn]
            if [dict(row) for row in rows] != expected:
                raise MigrationError('MIGRATION_VERIFICATION_FAILED')
            if store.query('SELECT count(*) AS n FROM tools')[0]['n']:
                raise MigrationError('EXECUTION_STATE_PRESENT')
        finally:
            store.close()
        # Reopening runs database integrity, event commit and projection validation.
        checked = open_store(config, channel)
        checked.close()
        if source.read_bytes() != original:
            raise MigrationError('SOURCE_CHANGED')
        if apply:
            # Publish with O_EXCL: neither an existing DB nor a racing new file can be replaced.
            # The validated private temporary file is copied into a private sibling before linking.
            with tempfile.NamedTemporaryFile(dir=parent, prefix='.migration-', delete=False) as output:
                staging = Path(output.name)
                try:
                    output.write(candidate.read_bytes()); output.flush(); os.fsync(output.fileno())
                    if tool_count:
                        backup = source.with_name(source.name + '.migration-backup')
                        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                        with os.fdopen(fd, 'wb') as stream:
                            stream.write(original); stream.flush(); os.fsync(stream.fileno())
                    os.link(staging, destination)
                finally:
                    staging.unlink(missing_ok=True)
    return dict(ok=True, applied=apply, lossless=not tool_count, turns=len(projected),
                source_messages=sum(map(len, turns)), destination_messages=2 * len(projected),
                omitted_tool_interactions=tool_count, source_preserved=True,
                text_digest=hashlib.sha256(json.dumps(projected, ensure_ascii=False).encode()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True); parser.add_argument('--destination', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--channel', choices=('cli', 'web'), default='cli')
    mode = parser.add_mutually_exclusive_group(); mode.add_argument('--dry-run', action='store_true'); mode.add_argument('--apply', action='store_true')
    parser.add_argument('--flatten-tool-history', action='store_true'); parser.add_argument('--confirm-lossy', action='store_true')
    args = vars(parser.parse_args()); args.pop('dry_run')
    try:
        result = migrate(**args)
    except MigrationError as exc:
        result = dict(ok=False, error_type=str(exc))
    except Exception:
        result = dict(ok=False, error_type='MIGRATION_FAILED_SOURCE_PRESERVED')
    print(json.dumps(result)); return 0 if result['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
