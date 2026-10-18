"""Bounded private before/after images from native Patch internals, never Git diff."""
from dataclasses import dataclass, replace
import difflib
import json
import os
import stat
import unicodedata

from ..tools.patch import ApplyPatchTool, sha, version, identity
from ..tools.undo_approval import undo_request


@dataclass(repr=False, frozen=True)
class ChangeEntry:
    relative_path: str
    original_existed: bool
    original_bytes: bytes
    original_sha256: str | None
    original_mode: int
    final_bytes: bytes
    final_sha256: str
    final_version: object
    attributes: object
    first_patch_revision: int
    last_patch_revision: int
    preexisting_git_state: str


def safe_text(text):
    return ''.join(c if c in '\n\t' or unicodedata.category(c) not in ('Cc', 'Cf') else ascii(c)[1:-1] for c in text)


class ChangeJournal:
    def __init__(self, baseline, patch_tool, settings, *, external_side_effects_possible=False):
        if type(patch_tool) is not ApplyPatchTool or patch_tool.patch_mode != 'write':
            raise ValueError('native_patch_required')
        self.baseline, self.patch_tool, self.settings = baseline, patch_tool, settings
        self.external_side_effects_possible = external_side_effects_possible
        self.entries = {}
        self._pending = None
        self.revision = 0
        self.active = True
        self.valid = True
        self.busy = False
        self.undo_status = 'undo_unavailable'
        self.current_git_files = baseline.files
        self.current_status_complete = baseline.complete
        self._historical = []

    def close(self):
        self.active = False
        self.entries.clear()
        self._pending = None

    @property
    def retained_bytes(self):
        return sum(len(e.original_bytes) + len(e.final_bytes) for e in self.entries.values())

    def before_publish(self, items):
        if not self.active or not self.valid: raise ValueError('journal_unavailable')
        if self.settings.undo_enabled and not self.baseline.unchanged(): raise ValueError('journal_baseline_incomplete_or_changed')
        if len(set(self.entries) | {i.path for i in items}) > self.settings.max_files:
            raise ValueError('journal_budget_exceeded')
        # Reserve peak retained snapshot memory, including old final images until commit.
        reserved = self.retained_bytes
        pending = dict(self.entries)
        states = {f['path']: f['status'] + ('_staged' if f['staged'] else '') for f in self.baseline.files}
        for item in items:
            old = self.entries.get(item.path)
            if old is not None:
                if (item.original is None or item.before != old.final_bytes or version(item.original) != old.final_version
                        or item.attributes != old.attributes): raise ValueError('journal_external_conflict')
                original, existed, mode, first = old.original_bytes, old.original_existed, old.original_mode, old.first_patch_revision
            else:
                original, existed = item.before, item.original is not None
                mode = stat.S_IMODE(item.original.st_mode) if existed else 0o600
                first = self.revision + 1
                reserved += len(original)
            reserved += len(item.after)
            if reserved > self.settings.max_journal_bytes: raise ValueError('journal_budget_exceeded')
            pending[item.path] = ChangeEntry(item.path, existed, original, sha(original) if existed else None,
                mode, item.after, sha(item.after), None, item.attributes, first, self.revision + 1,
                old.preexisting_git_state if old else states.get(item.path, 'clean_or_not_reported' if self.baseline.complete else 'unknown'))
        self._pending = pending

    def after_success(self, items):
        if not self.active or self._pending is None: raise ValueError('journal_commit_failed')
        pending = dict(self._pending)
        for item in items:
            fd, name, _ = self.patch_tool._open_parent(item.path)
            try: body, info, attributes = self.patch_tool._read(fd, name)
            finally: os.close(fd)
            if (body != item.after or attributes != item.attributes or identity(info) != identity(item.staged_info)
                    or stat.S_IMODE(info.st_mode) != pending[item.path].original_mode):
                raise ValueError('journal_commit_failed')
            pending[item.path] = replace(pending[item.path], final_version=version(info), attributes=attributes)
        self.entries = pending
        self._pending = None
        self.revision += 1
        self.undo_status = 'undo_available' if self.can_undo() else 'undo_unavailable'

    def on_failure(self, result):
        self._pending = None
        if result.metadata.get('status') in ('rollback_conflict', 'partial_failure_possible'):
            self.valid = False
            self.undo_status = 'undo_unavailable'

    def check_entry(self, entry):
        fd, name, _ = self.patch_tool._open_parent(entry.relative_path)
        try: body, info, attributes = self.patch_tool._read(fd, name)
        finally: os.close(fd)
        if (body != entry.final_bytes or sha(body) != entry.final_sha256 or version(info) != entry.final_version
                or attributes != entry.attributes): raise ValueError('undo_conflict_external_modification')
        return body, info, attributes

    def can_undo(self):
        if not (self.active and self.valid and self.settings.undo_enabled and self.entries and self.baseline.unchanged()
                and undo_request(self.entries.values()) is not None): return False
        try:
            for entry in self.entries.values(): self.check_entry(entry)
        except (OSError, ValueError): return False
        return True

    async def refresh(self):
        result = await self.baseline.tool.execute()
        self.current_status_complete = False
        if result.success:
            body = json.loads(result.output)
            self.current_git_files = body['files']
            self.current_status_complete = not body['truncated']

    def summary(self):
        files = []
        for entry in self.entries.values():
            try: self.check_entry(entry); matches = True
            except (OSError, ValueError): matches = False
            files.append({'path': entry.relative_path, 'source': 'native_patch',
                'operation': 'updated' if entry.original_existed else 'added',
                'preexisting_git_state': entry.preexisting_git_state,
                'original_sha256': entry.original_sha256, 'final_sha256': entry.final_sha256,
                'current_matches': matches, 'current_state': 'matches_agent_result' if matches else 'stale_review',
                'first_revision': entry.first_patch_revision, 'last_revision': entry.last_patch_revision})
        baseline_paths = {f['path'] for f in self.baseline.files}
        other = [{'path': f['path'], 'source': 'preexisting_user_or_external' if f['path'] in baseline_paths else 'unknown_external',
                  'staged': f['staged'], 'unstaged': f['unstaged'], 'untracked': f['untracked']}
                 for f in self.current_git_files if f['path'] not in self.entries]
        return {'agent_owned_files': len(files), 'preexisting_user_dirty_files': len(baseline_paths),
            'files': files or list(self._historical), 'other_git_changes': other, 'baseline': self.baseline.summary(),
            'git_metadata_unchanged': self.baseline.unchanged(), 'current_status_complete': self.current_status_complete,
            'external_side_effects_possible': self.external_side_effects_possible,
            'undo_status': self.undo_status, 'undo_eligible': self.can_undo(),
            'journal_valid': self.valid, 'review_scope': 'native Patch delta; Git status is not a complete filesystem audit'}

    def summary_text(self, limit=None):
        limit = min(limit or self.settings.max_review_chars, self.settings.max_review_chars)
        body = self.summary()
        body['review_truncated'] = False
        # Prefer counts and preserve an explicit omission marker over broken JSON.
        lists = [body['files'], body['other_git_changes'], body['baseline']['staged'],
                 body['baseline']['unstaged'], body['baseline']['untracked'], body['baseline']['conflicts']]
        while len(json.dumps(body, ensure_ascii=True)) > limit:
            target = max(lists, key=len)
            if not target:
                body = {'agent_owned_files': len(self.entries), 'undo_status': self.undo_status,
                        'undo_eligible': self.can_undo(), 'review_truncated': True}
                break
            target.pop(); body['review_truncated'] = True
        return json.dumps(body, ensure_ascii=True)

    def review(self):
        cap = self.settings.max_review_chars
        header = 'Task Change Review (Agent Diff is not Git Diff)\n'
        summary = self.summary_text(max(128, cap // 2))
        parts = [header, summary, '\nAgent-only Diff (historical if stale_review):\n']
        used = sum(map(len, parts)); truncated = False
        for entry in self.entries.values():
            lines = difflib.unified_diff(entry.original_bytes.decode('utf-8').splitlines(keepends=True),
                entry.final_bytes.decode('utf-8').splitlines(keepends=True),
                fromfile=('a/' + json.dumps(entry.relative_path, ensure_ascii=True)) if entry.original_existed else '/dev/null',
                tofile='b/' + json.dumps(entry.relative_path, ensure_ascii=True))
            for line in lines:
                if not line.endswith('\n'): line += '\n\\ No newline at end of file\n'
                room = max(0, cap - used - 80)
                piece = safe_text(line[:room])
                if len(piece) > room or len(line) > room:
                    parts.append(piece[:room]); truncated = True; break
                parts.append(piece); used += len(piece)
            if truncated: break
        if truncated: parts.append('\n[review_truncated: true; Diff omitted]\n')
        return ''.join(parts)[:cap]

    def consume(self, status):
        self._historical = [{'path': e.relative_path, 'operation': 'updated' if e.original_existed else 'added',
                             'undo_status': status} for e in self.entries.values()]
        self.entries.clear(); self._pending = None
        self.undo_status = status
        self.active = False
