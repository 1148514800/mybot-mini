"""Bounded turn-local requirement provenance, separate from revision verification.

Model input is a proposal. Only exact current-user quotes and observed versioned
native reads can establish provenance. No restored Session or model text grants
permissions or creates independent acceptance evidence.
"""
from dataclasses import dataclass, field, asdict
import hashlib
import json
import re
import time
import secrets
from copy import deepcopy

from ..tools.base import Tool, ToolResult

SOURCES = ('user_explicit', 'project_documented', 'agent_suggestion', 'unresolved')
CATEGORIES = ('functional', 'boundary', 'validation', 'integration', 'nonfunctional')
MAX_REQUIREMENTS = 12
MAX_TEXT = 320
MAX_BYTES = 16000


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    requirement_text: str
    source_type: str
    source_reference: str
    category: str
    added_version: int
    added_at: float


@dataclass
class TaskContract:
    user_input: str = field(repr=False)
    controller: object = field(repr=False)
    requirements: list = field(default_factory=list)
    task_id: str = field(default_factory=lambda: secrets.token_hex(16))
    version: int = 0
    claims: set = field(default_factory=set)
    links: dict = field(default_factory=dict)
    _reads: dict = field(default_factory=dict, repr=False)
    _tests: dict = field(default_factory=dict, repr=False)
    _independent: dict = field(default_factory=dict, repr=False)
    _invalidated: bool = False

    def observe_read(self, tool, arguments, result):
        from ..tools.read_file_range import ReadFileRangeTool
        if type(tool) is not ReadFileRangeTool or not result.success or len(self._reads) >= 12: return
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            target = tool.resolve(args['path'])
            version = result.metadata.get('file_sha256')
            if not version or hashlib.sha256(tool.read_bytes(target)).hexdigest() != version: return
            text = re.sub(r'^\d+ \| ', '', result.output, flags=re.M)
            ref = 'document-' + str(len(self._reads) + 1)
            self._reads[ref] = (target, version, text[:16000])
            result.metadata['contract_source_ref'] = ref
        except (ValueError, OSError, KeyError, TypeError): return

    def observe_test(self):
        c = self.controller
        if c.verification != 'valid' or c.last_verified_revision != c.current_revision: return
        ref = f'test-{c.test_runs}'
        if len(self._tests) < 32:
            self._tests[ref] = {'revision': c.current_revision, 'test_runs': c.test_runs,
                              'tests_passed': c.tests_passed_after_last_patch}

    def record(self, requirements=None, claims=None, evidence_links=None):
        requirements = [] if requirements is None else requirements
        claims = [] if claims is None else claims
        evidence_links = [] if evidence_links is None else evidence_links
        if not all(type(v) is list for v in (requirements, claims, evidence_links)):
            raise ValueError('invalid_contract_arrays')
        if len(requirements) + len(self.requirements) > MAX_REQUIREMENTS or len(claims) > 12 or len(evidence_links) > 12:
            raise ValueError('contract_limit')
        if len(json.dumps([requirements, claims, evidence_links], ensure_ascii=True).encode()) > MAX_BYTES:
            raise ValueError('contract_budget')
        pending = []
        ids = {r.requirement_id for r in self.requirements}
        for item in requirements:
            if type(item) is not dict or set(item) != {'requirement_id', 'requirement_text', 'source_type', 'source_reference', 'category'}:
                raise ValueError('invalid_requirement_fields')
            if any(type(v) is not str for v in item.values()): raise ValueError('invalid_requirement_type')
            ident, text, source, ref, category = (item[k] for k in
                ('requirement_id', 'requirement_text', 'source_type', 'source_reference', 'category'))
            if not re.fullmatch(r'R[1-9][0-9]?', ident) or ident in ids: raise ValueError('immutable_requirement_id')
            if not 1 <= len(text) <= MAX_TEXT or len(ref) > 80 or source not in SOURCES or category not in CATEGORIES:
                raise ValueError('invalid_requirement')
            if source == 'user_explicit':
                if ref != 'current-user' or text not in self.user_input: raise ValueError('unverified_user_quote')
            elif source == 'project_documented':
                read = self._reads.get(ref)
                if read is None: raise ValueError('unobserved_document')
                target, version, excerpt = read
                try: current = hashlib.sha256(target.read_bytes()).hexdigest()
                except OSError: raise ValueError('stale_document') from None
                if current != version or text not in excerpt: raise ValueError('stale_or_fabricated_document_quote')
            elif ref: raise ValueError('untrusted_source_requires_empty_reference')
            ids.add(ident)
            pending.append(Requirement(**item, added_version=self.version + 1, added_at=time.time()))
        if any(type(ident) is not str or ident not in ids for ident in claims): raise ValueError('unknown_claim')
        for link in evidence_links:
            if (type(link) is not dict or set(link) != {'requirement_id', 'evidence_ref'} or
                type(link['requirement_id']) is not str or type(link['evidence_ref']) is not str or
                link['requirement_id'] not in ids or link['evidence_ref'] not in self._tests):
                raise ValueError('unobserved_test_reference')
        if len(json.dumps([asdict(r) for r in self.requirements + pending], ensure_ascii=True).encode()) > 9000:
            raise ValueError('contract_total_budget')
        # Atomic append. No model deletion, replacement, source promotion or PASS setter.
        self.requirements.extend(pending)
        self.claims.update(claims)
        for link in evidence_links:
            self.links.setdefault(link['requirement_id'], set()).add(link['evidence_ref'])
        self.version += 1
        return self.snapshot()

    def verify_independently(self, requirement_id, assertion_id, assertion):
        """HOST ONLY: execute a trusted assertion, never accept model names/prose/results.

        No production oracle is installed. Harness code may register a callable
        independently of the model. Assertion content never enters model context.
        """
        c = self.controller
        if requirement_id not in {r.requirement_id for r in self.requirements}: raise ValueError('unknown_requirement')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', assertion_id): raise ValueError('invalid_assertion_id')
        revision = c.current_revision
        self._independent.pop(requirement_id, None)
        if self._invalidated or not c.check_hashes(): return False
        try: passed = assertion() is True
        except Exception: passed = False
        if passed and revision == c.current_revision and c.check_hashes():
            self._independent[requirement_id] = (revision, secrets.token_hex(8))
            return True
        return False

    def invalidate(self):
        self._invalidated = True

    def snapshot(self):
        c = self.controller
        current = not self._invalidated and c.check_hashes() and c.state not in ('cancelled', 'execution_uncertain')
        rows = []
        for r in self.requirements:
            refs = sorted(ref for ref in self.links.get(r.requirement_id, ())
                          if current and self._tests[ref]['revision'] == c.current_revision
                          and c.verification == 'valid')
            independent = self._independent.get(r.requirement_id)
            trusted = r.source_type in ('user_explicit', 'project_documented')
            verified = trusted and current and independent is not None and independent[0] == c.current_revision
            status = ('independently_verified' if verified else 'test_evidence_observed' if refs else
                      'implementation_claimed' if r.requirement_id in self.claims else 'identified')
            if r.source_type == 'project_documented':
                read = self._reads.get(r.source_reference)
                try: source_current = read is not None and hashlib.sha256(read[0].read_bytes()).hexdigest() == read[1]
                except OSError: source_current = False
                if not source_current:
                    trusted = False
                    verified = False
            if not trusted: status = 'unverified'
            elif c.state in ('blocked', 'cancelled', 'execution_uncertain', 'budget_exhausted') and not verified:
                status = 'blocked'
            rows.append({**{k: getattr(r, k) for k in r.__dataclass_fields__}, 'status': status,
                         'evidence_level': 3 if verified else 2 if refs else 1 if r.requirement_id in self.claims else 0,
                         'evidence_refs': (['acceptance-' + independent[1]] if verified else refs),
                         'reason': 'independent_assertion_passed' if verified else
                             'test_execution_observed_coverage_unknown' if refs else 'no_current_requirement_acceptance',
                         'current_revision': c.current_revision})
        trusted_rows = [r for r in rows if r['source_type'] in ('user_explicit', 'project_documented')]
        verified_count = sum(r['status'] == 'independently_verified' for r in trusted_rows)
        return deepcopy({'task_id': self.task_id, 'established': bool(rows), 'version': self.version, 'current_revision': c.current_revision,
                         'requirements': rows, 'user_explicit_count': sum(r['source_type'] == 'user_explicit' for r in rows),
                         'test_evidence_count': sum(r['status'] == 'test_evidence_observed' for r in trusted_rows),
                         'independently_verified_count': verified_count,
                         'missing_acceptance_count': len(trusted_rows) - verified_count,
                         'pending_conditions': any(r['source_type'] == 'unresolved' for r in rows),
                         'requirement_coverage': 'unknown' if not trusted_rows or verified_count < len(trusted_rows) else 'verified',
                         'task_correctness': 'unknown',
                         'observed_test_refs': list(self._tests)})

    def public_snapshot(self):
        # No private quotes, host paths, hashes, receipts or raw prompts in events.
        snapshot = self.snapshot()
        for r in snapshot['requirements']:
            r['requirement_text'] = '需求 ' + r['requirement_id'] + '（来源与证据状态见下）'  # bounded privacy-safe summary
            if r['source_type'] == 'user_explicit':
                raw = next(item.requirement_text for item in self.requirements if item.requirement_id == r['requirement_id'])
                start = self.user_input.index(raw)
                r['source_span'] = [start, start + len(raw)]
                r['source_message_chars'] = len(self.user_input)
            r.pop('source_reference', None)
        snapshot.pop('observed_test_refs', None)
        return snapshot

    def summary(self):
        s = self.snapshot()
        return (f"[TASK CONTRACT] established={s['established']} revision={s['current_revision']} "
                f"用户明确要求={s['user_explicit_count']} 测试记录关联={s['test_evidence_count']} "
                f"缺少独立验收={s['missing_acceptance_count']} 待确认={s['pending_conditions']} "
                'requirement_coverage=' + s['requirement_coverage'] + ' task_correctness=unknown')


class ContractTool(Tool):
    name = 'record_task_contract'
    provides_execution_evidence = False
    private_arguments = True
    description = ('Append up to 12 immutable requirements before editing; requirement_text must be an exact quote '
                   'from current-user or a native read_file_range contract_source_ref. Agent suggestions/unresolved '
                   'have empty source_reference. Claims are not evidence. evidence_links can reference host-observed '
                   'test-N only; testing does not prove requirement coverage. No deletion or independent PASS.')
    parameters = {'type': 'object', 'properties': {
        'requirements': {'type': 'array', 'maxItems': 12, 'items': {'type': 'object', 'properties': {
            'requirement_id': {'type': 'string'}, 'requirement_text': {'type': 'string', 'maxLength': MAX_TEXT},
            'source_type': {'type': 'string', 'enum': list(SOURCES)}, 'source_reference': {'type': 'string'},
            'category': {'type': 'string', 'enum': list(CATEGORIES)}},
            'required': ['requirement_id', 'requirement_text', 'source_type', 'source_reference', 'category'], 'additionalProperties': False}},
        'claims': {'type': 'array', 'maxItems': 12, 'items': {'type': 'string'}},
        'evidence_links': {'type': 'array', 'maxItems': 12, 'items': {'type': 'object', 'properties': {
            'requirement_id': {'type': 'string'}, 'evidence_ref': {'type': 'string'}},
            'required': ['requirement_id', 'evidence_ref'], 'additionalProperties': False}}}, 'additionalProperties': False}

    def __init__(self, owner): self.owner = owner

    async def execute(self, **kwargs):
        contract = self.owner.task_contract
        if contract is None: return ToolResult(False, error='contract_not_active')
        try:
            from ..tools.arguments import parse_object
            args = parse_object(kwargs, max_bytes=MAX_BYTES)
            return ToolResult(True, json.dumps(contract.record(**args), ensure_ascii=True))
        except (ValueError, TypeError, OverflowError):
            return ToolResult(False, error='contract_proposal_rejected')
