"""Reuse UAT schema, HTTP gate, settlement and SDK adapter; independent 16 cap."""
from contextlib import contextmanager
from pathlib import Path
import os,sqlite3,stat,time
from scripts.uat.budget import Ledger as OriginalLedger,BudgetClient,BudgetStop
from .plan import LIMITS,GLOBAL_LIMIT

SCHEMA='''CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE cases(id TEXT PRIMARY KEY,status TEXT NOT NULL);
CREATE TABLE reservations(id INTEGER PRIMARY KEY,case_id TEXT NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,purpose TEXT NOT NULL,created REAL NOT NULL,finished REAL,state TEXT NOT NULL,http_attempts INTEGER NOT NULL DEFAULT 0,usage TEXT,estimated INTEGER,error_type TEXT,status_code INTEGER);'''

def private_directory(path):
    path=Path(path).absolute()
    if path!=path.resolve():raise BudgetStop('symlink_or_noncanonical_private_path')
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    for p in (path,*path.parents):
        info=p.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,os.geteuid()):raise BudgetStop('unsafe_private_ancestor')
    info=path.stat()
    if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:raise BudgetStop('private_directory_required')
    return path

class Ledger(OriginalLedger):
    def __init__(self,path,plan_hash):
        self.path=Path(path).absolute();private_directory(self.path.parent);self.verify=lambda:None
        try:fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);new=True
        except FileExistsError:fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);new=False
        try:self.identity=(os.fstat(fd).st_dev,os.fstat(fd).st_ino)
        finally:os.close(fd)
        with self.connect() as db:
            if new:
                db.executescript('BEGIN IMMEDIATE;'+SCHEMA+'COMMIT;')
                db.execute("INSERT INTO meta VALUES('version','persistent_session_1')")
                db.execute("INSERT INTO meta VALUES('plan',?)",(plan_hash,))
            if db.execute("SELECT value FROM meta WHERE key='version'").fetchone()!=('persistent_session_1',):raise BudgetStop('ledger_version')
            if db.execute("SELECT value FROM meta WHERE key='plan'").fetchone()!=(plan_hash,):raise BudgetStop('plan_changed')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise BudgetStop('ledger_corrupt')
    @contextmanager
    def connect(self):
        db=None
        try:
            private_directory(self.path.parent);info=self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)&0o077 or (info.st_dev,info.st_ino)!=self.identity):raise BudgetStop('ledger_identity_or_permissions')
            db=sqlite3.connect(self.path,timeout=5,isolation_level='DEFERRED');db.execute('PRAGMA synchronous=FULL')
            with db:yield db
        except (sqlite3.Error,OSError):raise BudgetStop('ledger_unavailable') from None
        finally:
            if db is not None:db.close()
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
        blocked=False
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone():raise BudgetStop('batch_halted')
            if db.execute('SELECT status FROM cases WHERE id=?',(case,)).fetchone()!=('running',):raise BudgetStop('case_not_running')
            if db.execute('SELECT count(*) FROM reservations').fetchone()[0]>=GLOBAL_LIMIT:raise BudgetStop('global_budget_exhausted')
            if db.execute('SELECT count(*) FROM reservations WHERE case_id=?',(case,)).fetchone()[0]>=LIMITS[case]:raise BudgetStop('case_budget_exhausted')
            cursor=db.execute('INSERT INTO reservations(case_id,provider,model,purpose,created,state,estimated) VALUES(?,?,?,?,?,?,?)',(case,provider,model,purpose,time.time(),'reserved',estimated));rid=cursor.lastrowid
            if purpose!='agent':
                db.execute("UPDATE reservations SET state='blocked' WHERE id=?",(rid,));db.execute("INSERT OR REPLACE INTO meta VALUES('halt','unexpected_summary_or_purpose')");blocked=True
        if blocked:raise BudgetStop('unexpected_summary_or_purpose')
        return rid
    def http(self,reservation):
        self.verify();return super().http(reservation)
