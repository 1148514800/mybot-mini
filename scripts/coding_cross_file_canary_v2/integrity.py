"""Per-revision deltas and cumulative native Journal ownership, never implicit trust."""
import json
from pathlib import Path
from scripts.coding_workflow_canary_v1.integrity import digest_images
from scripts.uat.server import private_json
from scripts.persistent_uat.budget import BudgetStop
from .plan import ALLOWED
from .fixture import git

def allowed_hashes(images):return {n:images[n]['sha256'] for n in ALLOWED}

def validate_summary(summary,owned,initial,final,revision):
 files=summary.get('files',[])
 if (not summary.get('journal_valid') or not summary.get('git_metadata_unchanged') or
     len(files)!=len(owned) or {f.get('path') for f in files}!=owned):raise BudgetStop('native_journal_files_mismatch')
 for f in files:
  n=f['path']
  if (not f.get('current_matches') or f.get('original_sha256')!=initial[n] or
      f.get('final_sha256')!=final[n] or not 1<=f.get('first_revision',0)<=f.get('last_revision',0)<=revision):raise BudgetStop('native_journal_hash_mismatch')

class IntegrityGate:
 def __init__(self,root,record):self.root=Path(root);self.record=Path(record)
 def initialize(self):
  if self.record.exists():raise BudgetStop('integrity_record_exists')
  state=digest_images(self.root)
  private_json(self.record,dict(revision=0,head=git(self.root,'rev-parse','HEAD'),workspace=state,initial_hashes=allowed_hashes(state),git=digest_images(self.root,True),native_patch_chain=[]))
 def verify(self,journal=None):
  p=json.loads(self.record.read_text());actual=digest_images(self.root)
  if actual!=p['workspace'] or digest_images(self.root,True)!=p['git'] or git(self.root,'rev-parse','HEAD')!=p['head']:raise BudgetStop('unknown_workspace_or_git_drift')
  changed=set(git(self.root,'diff','--name-only','HEAD','--').splitlines())
  expected={n for n in ALLOWED if actual[n]['sha256']!=p['initial_hashes'][n]}
  if changed!=expected or len(p['native_patch_chain'])!=p['revision']:raise BudgetStop('git_diff_revision_mismatch')
  previous=p['initial_hashes'];owned=set()
  for i,e in enumerate(p['native_patch_chain'],1):
   after=e.get('after_hashes',{});delta={n for n in ALLOWED if after.get(n)!=previous.get(n)}
   if (e.get('revision')!=i or e.get('before_hashes')!=previous or set(after)!=set(ALLOWED) or
       not delta or set(e.get('changed_files',[]))!=delta or len(e['changed_files'])!=len(delta) or
       not e.get('receipt_commit_success') or not e.get('preview_to_commit_consistent')):raise BudgetStop('revision_chain_invalid')
   owned|=delta
   if set(e.get('cumulative_owned',[]))!=owned:raise BudgetStop('cumulative_ownership_mismatch')
   validate_summary(e.get('native_journal',{}),owned,p['initial_hashes'],after,i);previous=after
  if previous!=allowed_hashes(actual):raise BudgetStop('persisted_revision_hash_mismatch')
  if journal is not None:
   if journal.revision!=p['revision']:raise BudgetStop('native_journal_revision_mismatch')
   validate_summary(journal.summary(),owned,p['initial_hashes'],previous,p['revision'])
  return p
 def accept_native_patch(self,before,journal,result):
  previous=json.loads(self.record.read_text());now=digest_images(self.root);meta=result.metadata
  if (not result.success or not meta.get('receipt_commit_success') or not meta.get('preview_to_commit_consistent') or
      before!=previous or digest_images(self.root,True)!=previous['git'] or journal.revision!=previous['revision']+1):raise BudgetStop('native_receipt_or_revision_missing')
  delta={n for n in now.keys()|previous['workspace'].keys() if now.get(n)!=previous['workspace'].get(n)}
  if not delta or delta-set(ALLOWED) or set(meta.get('changed_files',[]))!=delta or meta.get('before_sha256')!={n:before['workspace'][n]['sha256'] for n in delta} or meta.get('after_sha256')!={n:now[n]['sha256'] for n in delta}:raise BudgetStop('patch_scope_or_delta_mismatch')
  owned=set().union(*(set(e['changed_files']) for e in previous['native_patch_chain']),delta)
  final=allowed_hashes(now);summary=journal.summary();validate_summary(summary,owned,previous['initial_hashes'],final,journal.revision)
  previous['native_patch_chain'].append(dict(revision=journal.revision,before_hashes=allowed_hashes(before['workspace']),after_hashes=final,changed_files=sorted(delta),cumulative_owned=sorted(owned),receipt_commit_success=True,preview_to_commit_consistent=True,native_journal=summary))
  previous.update(workspace=now,revision=journal.revision);private_json(self.record,previous);return self.verify(journal)
 def both_legally_changed(self):
  p=self.verify();owned=set().union(*(set(e['changed_files']) for e in p['native_patch_chain']))
  return owned==set(ALLOWED) and all(p['workspace'][n]['sha256']!=p['initial_hashes'][n] for n in ALLOWED)
