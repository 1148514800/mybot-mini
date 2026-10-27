"""Reuse durable reservations/HTTP accounting; new C01 12-cap schema identity."""
from scripts.streaming_steer_recovery_v3.budget import BudgetStop,private_directory
from scripts.persistent_uat.budget import Ledger as SchemaLedger
from scripts.streaming_steer_real_uat_v2.budget import Ledger as Rules
from .plan import GLOBAL_LIMIT,LIMITS
# Only constants are specialized; persistence, HTTP and settlement remain original.
import time
class Ledger(SchemaLedger):
 halt=Rules.halt
 finish=Rules.finish
 def start(self,case):
  if case!='C01':raise BudgetStop('unknown_case')
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute("select 1 from meta where key='halt'").fetchone() or db.execute('select 1 from cases').fetchone() or db.execute('select 1 from reservations').fetchone():raise BudgetStop('halt_or_attempt_exists_no_replay')
   db.execute("insert into cases values('C01','running')")
 def reserve(self,case,provider,model,purpose,estimated):
  self.verify()
  reason=None
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute("select 1 from meta where key='halt'").fetchone():raise BudgetStop('batch_halted')
   if db.execute("select 1 from reservations where state='reserved'").fetchone():raise BudgetStop('unsettled_request')
   if case!='C01' or db.execute("select status from cases where id='C01'").fetchone()!=('running',):raise BudgetStop('case_not_running')
   if db.execute('select count(*) from reservations').fetchone()[0]>=GLOBAL_LIMIT:reason='physical_budget_exhausted'
   if purpose!='agent':reason='summary_or_judge_forbidden'
   if reason:db.execute("insert or ignore into meta values('halt',?)",(reason,))
   else:rid=db.execute("insert into reservations(case_id,provider,model,purpose,created,state,estimated) values(?,?,?,?,?,'reserved',?)",(case,provider,model,purpose,time.time(),estimated)).lastrowid

  if reason:raise BudgetStop(reason)
  return rid
