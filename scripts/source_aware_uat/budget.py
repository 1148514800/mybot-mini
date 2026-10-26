"""Independent ten-request ledger; reuse original identity/HTTP/SDK/settlement gates."""
import time
from scripts.persistent_uat.budget import Ledger as PersistentLedger,private_directory,BudgetClient,BudgetStop
from .plan import LIMITS,GLOBAL_LIMIT

class Ledger(PersistentLedger):
    def start(self,case):
        if case not in LIMITS:raise BudgetStop('unknown_case')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone():raise BudgetStop('batch_halted')
            if db.execute("SELECT 1 FROM reservations WHERE state='reserved'").fetchone():raise BudgetStop('unsettled_request')
            previous=[r[0] for r in db.execute('SELECT id FROM cases ORDER BY rowid')]
            if case in previous:raise BudgetStop('case_already_started_no_reruns')
            if previous!=list(LIMITS)[:list(LIMITS).index(case)] or db.execute("SELECT 1 FROM cases WHERE status='running'").fetchone():raise BudgetStop('case_order_or_running')
            db.execute("INSERT INTO cases VALUES(?,'running')",(case,))
    def reserve(self,case,provider,model,purpose,estimated):
        self.verify()
        if case not in LIMITS:raise BudgetStop('unknown_case')
        reason=None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone():raise BudgetStop('batch_halted')
            if db.execute("SELECT 1 FROM reservations WHERE state='reserved'").fetchone():raise BudgetStop('unsettled_request')
            if db.execute('SELECT status FROM cases WHERE id=?',(case,)).fetchone()!=('running',):raise BudgetStop('case_not_running')
            if db.execute('SELECT count(*) FROM reservations').fetchone()[0]>=GLOBAL_LIMIT:reason='global_budget_exhausted'
            elif db.execute('SELECT count(*) FROM reservations WHERE case_id=?',(case,)).fetchone()[0]>=LIMITS[case]:reason='case_budget_exhausted'
            if reason:db.execute("INSERT OR REPLACE INTO meta VALUES('halt',?)",(reason,))
            else:
                cursor=db.execute('INSERT INTO reservations(case_id,provider,model,purpose,created,state,estimated) VALUES(?,?,?,?,?,?,?)',(case,provider,model,purpose,time.time(),'reserved',estimated));rid=cursor.lastrowid
                if purpose!='agent':
                    reason='unexpected_summary_or_purpose';db.execute("UPDATE reservations SET state='blocked' WHERE id=?",(rid,));db.execute("INSERT OR REPLACE INTO meta VALUES('halt',?)",(reason,))
        if reason:raise BudgetStop(reason)
        return rid
    def finish(self,case):
        with self.connect() as db:
            if db.execute("SELECT 1 FROM reservations WHERE state='reserved'").fetchone():raise BudgetStop('unsettled_request')
            if db.execute('SELECT status FROM cases WHERE id=?',(case,)).fetchone()!=('running',):raise BudgetStop('case_not_running')
            db.execute("UPDATE cases SET status='finished' WHERE id=?",(case,))
