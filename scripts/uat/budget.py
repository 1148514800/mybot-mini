"""Durable, fail-closed UAT reservations at both SDK create and HTTP boundaries."""
from __future__ import annotations
import asyncio
from contextvars import ContextVar
import json, os, sqlite3, time
from pathlib import Path
from types import SimpleNamespace
from mybot.runtime_accounting import CURRENT, usage_values
from mybot.agent.token_counter import TokenCounter

RESERVATION = ContextVar('uat_reservation', default=None)
LIMITS = {'U01':2,'U02':4,'U03':6,'U04':14,'U05':14,'U06':8}

class BudgetStop(RuntimeError): pass

class Ledger:
    def __init__(self, path, plan_hash):
        self.path=Path(path); self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.path.is_symlink():raise BudgetStop('unsafe_ledger')
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reservations(id INTEGER PRIMARY KEY,case_id TEXT NOT NULL,
                provider TEXT NOT NULL,model TEXT NOT NULL,purpose TEXT NOT NULL,created REAL NOT NULL,
                finished REAL,state TEXT NOT NULL,http_attempts INTEGER NOT NULL DEFAULT 0,
                usage TEXT,estimated INTEGER,error_type TEXT,status_code INTEGER);''')
            row=db.execute("SELECT value FROM meta WHERE key='plan'").fetchone()
            if row and row[0]!=plan_hash:raise BudgetStop('plan_changed')
            db.execute("INSERT OR IGNORE INTO meta VALUES('plan',?)",(plan_hash,))
        os.chmod(self.path,0o600)
    def connect(self):
        db=sqlite3.connect(self.path,timeout=5,isolation_level='DEFERRED')
        db.execute('PRAGMA synchronous=FULL'); return db
    def halt(self, reason):
        with self.connect() as db:db.execute("INSERT OR REPLACE INTO meta VALUES('halt',?)",(reason,))
    def start(self, case):
        if case not in LIMITS:raise BudgetStop('unknown_case')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone():raise BudgetStop('batch_halted')
            if db.execute("SELECT 1 FROM cases WHERE status='running'").fetchone():raise BudgetStop('another_case_running')
            row=db.execute('SELECT status FROM cases WHERE id=?',(case,)).fetchone()
            if row:raise BudgetStop('case_already_started_no_reruns')
            db.execute("INSERT INTO cases VALUES(?,'running')",(case,))
    def finish(self,case):
        with self.connect() as db:db.execute("UPDATE cases SET status='finished' WHERE id=?",(case,))
    def reserve(self,case,provider,model,purpose,estimated):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone():raise BudgetStop('batch_halted')
            if db.execute("SELECT status FROM cases WHERE id=?",(case,)).fetchone()!=('running',):raise BudgetStop('case_not_running')
            total=db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0]
            count=db.execute('SELECT COUNT(*) FROM reservations WHERE case_id=?',(case,)).fetchone()[0]
            if total>=48:raise BudgetStop('global_budget_exhausted')
            if count>=LIMITS[case]:raise BudgetStop('case_budget_exhausted')
            cursor=db.execute('INSERT INTO reservations(case_id,provider,model,purpose,created,state,estimated) VALUES(?,?,?,?,?,?,?)',
                (case,provider,model,purpose,time.time(),'reserved',estimated))
            return cursor.lastrowid  # transaction commits before the SDK invocation
    def http(self, reservation):
        repeated=False
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT http_attempts,state FROM reservations WHERE id=?',(reservation,)).fetchone()
            if not row or row[0]!=0 or row[1]!='reserved':
                db.execute("INSERT OR REPLACE INTO meta VALUES('halt','unaccounted_or_repeated_http')")
                repeated=True
            else:db.execute('UPDATE reservations SET http_attempts=1 WHERE id=?',(reservation,))
        if repeated:raise BudgetStop('implicit_retry_or_unreserved_http')
    def settle(self,reservation,state,usage=None,exc=None):
        code=getattr(exc,'status_code',None)
        if type(code) is not int:code=None
        with self.connect() as db:
            db.execute('UPDATE reservations SET finished=?,state=?,usage=?,error_type=?,status_code=? WHERE id=?',
                (time.time(),state,json.dumps(usage_values(usage)),type(exc).__name__ if exc else None,code,reservation))
            if code in (401,403):db.execute("INSERT OR REPLACE INTO meta VALUES('halt','authentication_failed')")
    def rows(self):
        with self.connect() as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM reservations ORDER BY id')]

class BudgetClient:
    def __init__(self,original,config,ledger,case,observe=None):
        self.original=original;self._client=original._client
        if original.max_retries!=0:raise BudgetStop('sdk_retries_not_zero')
        self.config=config;self.ledger=ledger;self.case=case;self.observe=observe
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
        async def gate(request):
            token=RESERVATION.get()
            if token is None or token[0] is not self.ledger:raise BudgetStop('http_without_reservation')
            if asyncio.current_task().cancelling():raise asyncio.CancelledError()
            self.ledger.http(token[1])
        self._client.event_hooks['request'].insert(0,gate)
    async def create(self,**request):
        if asyncio.current_task().cancelling():raise asyncio.CancelledError()
        if self.original.max_retries!=0:raise BudgetStop('sdk_retries_changed')
        accounting=CURRENT.get();purpose=accounting.purpose if accounting else 'unknown'
        estimated=TokenCounter.measure(request)['estimated_input_tokens']
        reservation=self.ledger.reserve(self.case,self.config.provider,self.config.model,purpose,estimated)
        token=RESERVATION.set((self.ledger,reservation))
        try:
            response=await self.original.chat.completions.create(**request)
            self.ledger.settle(reservation,'returned',getattr(response,'usage',None))
            if self.observe:self.observe(reservation,purpose,request,response)
            return response
        except BaseException as exc:
            self.ledger.settle(reservation,'cancelled' if isinstance(exc,asyncio.CancelledError) else 'failed',exc=exc)
            raise
        finally:RESERVATION.reset(token)
    async def close(self):await self.original.close()
