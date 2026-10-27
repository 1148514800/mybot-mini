"""Revision-aware integrity: never whitelist a changed file without native evidence."""
import hashlib,json
from pathlib import Path
from mybot.evaluation.coding_fixtures import snapshot
from scripts.uat.server import private_json
from scripts.persistent_uat.budget import BudgetStop
from .plan import ALLOWED
from .fixture import git

def digest_images(root,git_only=False):
 data=snapshot(root,exclude_git=False)
 return {n:dict(sha256=hashlib.sha256(im.data).hexdigest(),mode=im.mode) for n,im in data.items() if (n.startswith('.git/') if git_only else not n.startswith('.git/'))}
class IntegrityGate:
 def __init__(self,root,record):self.root=Path(root);self.record=Path(record)
 def initialize(self):
  if self.record.exists():raise BudgetStop('integrity_record_exists')
  private_json(self.record,dict(revision=0,head=git(self.root,'rev-parse','HEAD'),workspace=digest_images(self.root),git=digest_images(self.root,True),native_patch_chain=[]))
 def verify(self,journal=None):
  p=json.loads(self.record.read_text())
  if digest_images(self.root)!=p['workspace'] or digest_images(self.root,True)!=p['git'] or git(self.root,'rev-parse','HEAD')!=p['head']:raise BudgetStop('unknown_workspace_or_git_drift')
  changed=git(self.root,'diff','--name-only','HEAD','--').splitlines()
  if set(changed)-{ALLOWED} or bool(changed)!=bool(p['revision']):raise BudgetStop('git_diff_revision_mismatch')
  if len(p['native_patch_chain'])!=p['revision']:raise BudgetStop('journal_chain_mismatch')
  previous=None
  for i,entry in enumerate(p['native_patch_chain'],1):
   summary=entry.get('native_journal',{});files=summary.get('files',[])
   if entry.get('revision')!=i or not entry.get('receipt_commit_success') or not entry.get('preview_to_commit_consistent') or not summary.get('journal_valid') or not summary.get('git_metadata_unchanged') or len(files)!=1 or files[0].get('path')!=ALLOWED or not files[0].get('current_matches') or files[0].get('final_sha256')!=entry.get('after_sha256') or (previous is not None and entry.get('before_sha256')!=previous):raise BudgetStop('persisted_native_journal_invalid')
   previous=entry['after_sha256']
  if previous is not None and previous!=p['workspace'][ALLOWED]['sha256']:raise BudgetStop('persisted_revision_hash_mismatch')
  if journal is not None:
   s=journal.summary()
   if journal.revision!=p['revision'] or not s['journal_valid'] or not s['git_metadata_unchanged'] or any(not f['current_matches'] for f in s['files']):raise BudgetStop('native_journal_revision_mismatch')
  return p
 def accept_native_patch(self,before,journal,result):
  if not result.success or not result.metadata.get('receipt_commit_success'):raise BudgetStop('native_receipt_missing')
  previous=json.loads(self.record.read_text());now=digest_images(self.root);summary=journal.summary()
  if before!=previous or digest_images(self.root,True)!=previous['git'] or journal.revision!=previous['revision']+1 or not summary['journal_valid'] or not summary['git_metadata_unchanged']:raise BudgetStop('native_journal_commit_mismatch')
  changed={n for n in now.keys()|previous['workspace'].keys() if now.get(n)!=previous['workspace'].get(n)}
  files=summary['files']
  if changed!={ALLOWED} or len(files)!=1 or files[0]['path']!=ALLOWED or not files[0]['current_matches'] or files[0]['final_sha256']!=now[ALLOWED]['sha256']:raise BudgetStop('patch_scope_or_journal_mismatch')
  previous['workspace']=now;previous['revision']=journal.revision;previous['native_patch_chain'].append(dict(revision=journal.revision,before_sha256=before['workspace'][ALLOWED]['sha256'],after_sha256=now[ALLOWED]['sha256'],preview_to_commit_consistent=result.metadata.get('preview_to_commit_consistent') is True,receipt_commit_success=True,native_journal=summary))
  private_json(self.record,previous);return self.verify(journal)
