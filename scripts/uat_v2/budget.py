"""Versioned caps; reuse the original durable schema, settlement and HTTP gate."""
import time
from types import MappingProxyType
from scripts.uat.budget import Ledger as OriginalLedger, BudgetClient, BudgetStop

LIMITS = MappingProxyType({'T01':12, 'T02':14, 'T03':8})
GLOBAL_LIMIT = 34


class Ledger(OriginalLedger):
    def start(self, case):
        if case not in LIMITS: raise BudgetStop('unknown_v2_case')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone(): raise BudgetStop('batch_halted')
            if db.execute("SELECT 1 FROM cases WHERE status='running'").fetchone(): raise BudgetStop('another_case_running')
            if db.execute('SELECT 1 FROM cases WHERE id=?',(case,)).fetchone(): raise BudgetStop('case_already_started_no_reruns')
            db.execute("INSERT INTO cases VALUES(?,'running')",(case,))

    def reserve(self, case, provider, model, purpose, estimated):
        if case not in LIMITS: raise BudgetStop('unknown_v2_case')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone(): raise BudgetStop('batch_halted')
            if db.execute('SELECT status FROM cases WHERE id=?',(case,)).fetchone()!=('running',): raise BudgetStop('case_not_running')
            total=db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0]
            count=db.execute('SELECT COUNT(*) FROM reservations WHERE case_id=?',(case,)).fetchone()[0]
            if total>=GLOBAL_LIMIT: raise BudgetStop('global_budget_exhausted')
            if count>=LIMITS[case]: raise BudgetStop('case_budget_exhausted')
            cursor=db.execute('INSERT INTO reservations(case_id,provider,model,purpose,created,state,estimated) VALUES(?,?,?,?,?,?,?)',
                (case,provider,model,purpose,time.time(),'reserved',estimated))
            return cursor.lastrowid
