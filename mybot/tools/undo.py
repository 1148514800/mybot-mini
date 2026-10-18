"""Host-only bounded Undo. No shell, Git writes, registry entry or persistent capsule."""
import json
import os
import stat

from .patch import ApplyPatchTool, Prepared, identity, version, sha
from .undo_approval import undo_request, authorize_undo


class UndoTransaction(ApplyPatchTool):
    """Reuse Patch fd/path/metadata/staging/recovery; remove is internal only."""
    def _recheck(self, item, *, published=False):
        if item.op == 'remove' and published:
            fd, name, _ = self._open_parent(item.path)
            try:
                if identity(os.fstat(fd)) != identity(os.fstat(item.parent)): raise ValueError('path_changed')
                try: os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError: return
                raise ValueError('undo_conflict_external_modification')
            finally: os.close(fd)
        return super()._recheck(item, published=published)

    def _stage(self, item):
        if item.op == 'remove':
            item.backup, _ = self._temp(item, item.before, stat.S_IMODE(item.original.st_mode))
        else: super()._stage(item)

    def _publish(self, item):
        if item.op == 'remove': os.unlink(item.name, dir_fd=item.parent)
        else: super()._publish(item)

    def _recover(self, attempted):
        conflict = False; uncertain = False
        for item in reversed(attempted):
            if item.op != 'remove':
                result = super()._recover([item])
                conflict |= result == 'rollback_conflict'
                uncertain |= result == 'partial_failure_possible'
                continue
            try:
                try:
                    self._recheck(item)
                    continue
                except (OSError, ValueError): pass
                self._recheck(item, published=True)
                data, info, attrs = self._read(item.parent, item.backup)
                if (data != item.before or attrs != item.attributes or identity(info) != item.temp_inodes[item.backup]
                        or stat.S_IMODE(info.st_mode) != stat.S_IMODE(item.original.st_mode)):
                    raise ValueError('rollback_backup_changed')
                backup_identity = identity(info)
                os.link(item.backup, item.name, src_dir_fd=item.parent, dst_dir_fd=item.parent, follow_symlinks=False)
                os.unlink(item.backup, dir_fd=item.parent); item.backup = None
                restored, info, attrs = self._read(item.parent, item.name)
                if (restored != item.before or attrs != item.attributes or identity(info) != backup_identity
                        or stat.S_IMODE(info.st_mode) != stat.S_IMODE(item.original.st_mode)):
                    raise OSError('undo_recovery_failed')
            except ValueError: conflict = True
            except Exception: uncertain = True
        return 'undo_partial_failure_possible' if uncertain or conflict else 'undo_rolled_back'

    @staticmethod
    def cleanup(items):
        failed = False
        for item in items:
            for name, expected in item.temp_inodes.items():
                try:
                    info = os.stat(name, dir_fd=item.parent, follow_symlinks=False)
                    if identity(info) != expected: failed = True; continue
                    os.unlink(name, dir_fd=item.parent)
                except FileNotFoundError: pass
                except OSError: failed = True
            os.close(item.parent)
        return failed


class UndoService:
    def __init__(self, journal, provider=None):
        self.journal, self.provider = journal, provider
        self.transaction = UndoTransaction(journal.patch_tool.workspace, patch_mode='write')

    def _metadata_check(self):
        j = self.journal
        if not j.active or not j.valid or not j.settings.undo_enabled or not j.entries:
            raise ValueError('undo_unavailable')
        if not j.baseline.unchanged(): raise ValueError('undo_conflict_git_metadata')

    def _preflight(self):
        self._metadata_check()
        items = []
        try:
            for entry in sorted(self.journal.entries.values(), key=lambda e: e.relative_path):
                fd, name, path = self.transaction._open_parent(entry.relative_path)
                item = Prepared(path, 'update' if entry.original_existed else 'remove', fd, name,
                    entry.final_bytes, entry.original_bytes, None)
                items.append(item)
                data, info, attrs = self.transaction._read(fd, name)
                if (data != entry.final_bytes or version(info) != entry.final_version or attrs != entry.attributes
                        or stat.S_IMODE(info.st_mode) != entry.original_mode):
                    raise ValueError('undo_conflict_external_modification')
                item.original, item.attributes = info, attrs
                self.transaction._recheck(item)
            self._metadata_check()
            return items
        except BaseException:
            self.transaction.cleanup(items)
            raise

    def _index_unchanged(self):
        try: return self.journal.baseline.scope.fingerprint()[0] == self.journal.baseline.fingerprint[0]
        except (OSError, ValueError, AttributeError): return False

    async def undo(self):
        j = self.journal
        if j.busy: return {'undo_status': 'undo_unavailable', 'conflicts': ['undo_busy'], 'verification_invalidated': False}
        j.busy = True
        items = []; attempted = []; approval = 'not_requested'; status = 'undo_unavailable'; reason = ''
        affected = []; restored = []; removed = []; before = {}; after = {}
        try:
            self._metadata_check()
            # Initial full preflight is disposed BEFORE await: /clear can drop all private images.
            preview = self._preflight()
            self.transaction.cleanup(preview); del preview
            request = undo_request(j.entries.values())
            if request is None: raise ValueError('undo_approval_uninspectable')
            j.undo_status = 'undo_previewed'
            if not await authorize_undo(self.provider, request):
                status = 'undo_denied'; approval = 'denied'
            else:
                approval = 'approved'; j.undo_status = 'undo_approved'
                # No awaits from the repeated preflight through publication/recovery/cleanup.
                self._metadata_check()
                if undo_request(j.entries.values()) != request: raise ValueError('undo_conflict_capsule_changed')
                items = self._preflight()
                affected = [i.path for i in items]
                before = {i.path: sha(i.before) for i in items}
                after = {i.path: sha(i.after) if i.op == 'update' else None for i in items}
                for item in items: self.transaction._stage(item)
                for item in items: self.transaction._recheck(item)
                self._metadata_check()
                for item in items:
                    self._metadata_check(); self.transaction._recheck(item)
                    attempted.append(item)
                    self.transaction._publish(item)
                    self.transaction._recheck(item, published=True)
                for item in items: self.transaction._recheck(item, published=True)
                self._metadata_check()
                status = 'undo_completed'
                restored = [i.path for i in items if i.op == 'update']
                removed = [i.path for i in items if i.op == 'remove']
        except (OSError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) and str(exc).isidentifier() else 'undo_conflict_file_state'
            status = self.transaction._recover(attempted) if attempted else ('undo_unavailable' if reason in ('undo_unavailable', 'undo_approval_uninspectable') else 'undo_conflict')
        except Exception:
            reason = 'undo_execution_failed'
            status = self.transaction._recover(attempted) if attempted else 'undo_unavailable'
        finally:
            if self.transaction.cleanup(items): status = 'undo_partial_failure_possible'
            j.busy = False
        invalidated = bool(attempted) or status in ('undo_conflict', 'undo_partial_failure_possible')
        index_unchanged = self._index_unchanged()
        if attempted or status == 'undo_partial_failure_possible': j.consume(status)
        else: j.undo_status = status
        return {'undo_status': status, 'affected_files': affected, 'restored_files': restored if status == 'undo_completed' else [],
            'removed_added_files': removed if status == 'undo_completed' else [], 'before_hashes': before, 'after_hashes': after,
            'index_unchanged': index_unchanged, 'conflicts': [reason] if reason else [],
            'approval_status': approval, 'files_may_have_changed': bool(attempted), 'verification_invalidated': invalidated}
