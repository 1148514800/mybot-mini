"""SQLite facts and transactional projections. Per-operation connections; no ORM.

Only the owner can access a private directory/file. Same-UID hostile processes
and SQLite/external filesystem crash atomicity are outside this boundary.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from .event_schema import Event,StoreError,VERSION,identifier,validate,STATUSES

DB_VERSION=2
APP_ID=0x4D594231
COMMITS_SCHEMA="""CREATE TABLE event_commits(session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 start_sequence INTEGER NOT NULL, end_sequence INTEGER NOT NULL, PRIMARY KEY(session_id,end_sequence));"""
DEFAULT_LIMITS={'max_bytes':64*1024*1024,'max_events':50000,'max_payload_bytes':65536}
SCHEMA='''
CREATE TABLE sessions(id TEXT PRIMARY KEY, namespace TEXT NOT NULL, workspace TEXT NOT NULL,
 title TEXT NOT NULL, created REAL NOT NULL, seq INTEGER NOT NULL DEFAULT 0,
 context_after INTEGER NOT NULL DEFAULT 0, pin_revision INTEGER NOT NULL DEFAULT 0);
CREATE INDEX session_namespace ON sessions(namespace,created DESC);
CREATE TABLE events(session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 event_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
 timestamp REAL NOT NULL, payload TEXT NOT NULL, source TEXT NOT NULL, privacy_class TEXT NOT NULL,
 schema_version INTEGER NOT NULL, canonical TEXT NOT NULL, UNIQUE(session_id,sequence));
CREATE INDEX event_types ON events(session_id,event_type,sequence);
CREATE TABLE messages(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 turn_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, truncated INTEGER NOT NULL,
 timestamp REAL NOT NULL, sequence INTEGER NOT NULL);
CREATE INDEX message_history ON messages(session_id,sequence DESC);
CREATE INDEX message_turn ON messages(turn_id,sequence);
CREATE TABLE turns(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL, state TEXT NOT NULL, owner_pid INTEGER NOT NULL DEFAULT 0, sequence INTEGER NOT NULL);
CREATE INDEX recent_turns ON turns(session_id,sequence DESC);
CREATE TABLE tools(id TEXT PRIMARY KEY, turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
 name TEXT NOT NULL, side_effect INTEGER NOT NULL, state TEXT NOT NULL, effect TEXT NOT NULL DEFAULT 'none');
CREATE INDEX turn_tools ON tools(turn_id,state);
CREATE TABLE pins(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 category TEXT NOT NULL, content TEXT NOT NULL, source_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
 start INTEGER NOT NULL, end INTEGER NOT NULL, created_at REAL NOT NULL, revision INTEGER NOT NULL,
 status TEXT NOT NULL, superseded_by TEXT);
CREATE INDEX active_pins ON pins(session_id,status,revision);
'''


def limits(value=None):
    value={} if value is None else value
    if type(value) is not dict or set(value)-DEFAULT_LIMITS.keys(): raise ValueError('event_limits')
    result=DEFAULT_LIMITS|value
    for key,lo,hi in [('max_bytes',1024*1024,256*1024*1024),('max_events',1,100000),('max_payload_bytes',1024,65536)]:
        if type(result[key]) is not int or not lo<=result[key]<=hi:raise ValueError('event_limit_'+key)
    return result


def _identity(st):return st.st_dev,st.st_ino


class SessionEventStore:
    def __init__(self,path,workspace,*,namespace='cli',settings=None,secrets=()):
        self.path=Path(path).expanduser().absolute();self.workspace=Path(workspace).resolve()
        self.namespace=namespace;self.workspace_ref=hashlib.sha256(os.fsencode(self.workspace)).hexdigest()
        self.secrets=tuple(secrets);self.limits=limits(settings);self._anchor=None;self._db_fd=None
        try:
            self._secure_path()
            if not self._new:self._recover_and_verify_existing()
            with self.connection() as db:
                if self._new:
                    db.executescript('BEGIN IMMEDIATE;'+SCHEMA+COMMITS_SCHEMA+f'PRAGMA application_id={APP_ID}; PRAGMA user_version={DB_VERSION}; COMMIT;')
                if db.execute('PRAGMA user_version').fetchone()[0]==1:
                    # Add only a commit-boundary index. Never invent old transaction boundaries.
                    db.execute('BEGIN IMMEDIATE')
                    try:
                        if db.execute('PRAGMA user_version').fetchone()[0]==1:
                            db.execute(COMMITS_SCHEMA)
                            db.execute('INSERT INTO event_commits SELECT id,seq,seq FROM sessions WHERE seq>0')
                            db.execute('PRAGMA user_version=2')
                        db.execute('COMMIT')
                    except BaseException:
                        db.execute('ROLLBACK');raise
                if db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID or db.execute('PRAGMA user_version').fetchone()[0]!=DB_VERSION:
                    raise StoreError('unsupported_database_version')
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise StoreError('database_integrity')
                expected={'sessions','events','messages','turns','tools','pins','event_commits'}
                if {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} != expected:raise StoreError('database_schema')
            if self._new:
                os.fsync(self._db_fd);os.fsync(self._anchor)
        except Exception as exc:
            self.close()
            if isinstance(exc,StoreError):raise
            raise StoreError('database_open_failed_original_preserved') from None

    def _secure_path(self):
        if self.path.is_relative_to(self.workspace) or self.path.resolve().is_relative_to(self.workspace):raise StoreError('storage_inside_workspace')
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY);parent=self.path.parent
        try:
            for part in parent.parts[1:]:
                try:os.mkdir(part,0o700,dir_fd=fd)
                except FileExistsError:pass
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=child
                info=os.fstat(fd)
                if info.st_uid not in (0,os.geteuid()):raise StoreError('storage_ancestor_owner')
            info=os.fstat(fd)
            if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:raise StoreError('storage_directory_not_private')
            self._anchor=fd;fd=None;self._parent_identity=_identity(info)
            try:
                self._db_fd=os.open(self.path.name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self._anchor);self._new=True
            except FileExistsError:
                self._db_fd=os.open(self.path.name,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self._anchor);self._new=False
            self._db_identity=_identity(os.fstat(self._db_fd));self._guard()
        finally:
            if fd is not None:os.close(fd)

    def _recover_and_verify_existing(self):
        try:
            self._verify_existing()
            return
        except sqlite3.OperationalError as exc:
            # Read-only SQLite cannot roll back a hot journal after process death.
            # Only this explicit recovery code may open a recognized v1 file RW.
            if getattr(exc,'sqlite_errorcode',None)!=sqlite3.SQLITE_READONLY_ROLLBACK:
                raise
        self._guard()
        header=os.pread(self._db_fd,100,0)
        if (len(header)!=100 or header[:16]!=b'SQLite format 3\x00'
            or int.from_bytes(header[60:64],'big') not in (1,DB_VERSION)
            or int.from_bytes(header[68:72],'big')!=APP_ID):
            raise StoreError('unsupported_database_version')
        db=sqlite3.connect(str(self.path),timeout=2,isolation_level=None)
        try:
            # SQLite owns locking, journal detection and rollback, never rebuild.
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID:
                raise StoreError('unsupported_database_version')
        finally:db.close()
        self._verify_existing()

    def _verify_existing(self):
        from urllib.parse import quote
        if os.fstat(self._db_fd).st_size<100 or os.pread(self._db_fd,16,0)!=b'SQLite format 3\x00':raise StoreError('database_header_invalid_original_preserved')
        db=sqlite3.connect('file:'+quote(str(self.path))+'?mode=ro',uri=True)
        try:
            if db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID or db.execute('PRAGMA user_version').fetchone()[0] not in (1,DB_VERSION):raise StoreError('unsupported_database_version')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise StoreError('database_integrity')
            version=db.execute('PRAGMA user_version').fetchone()[0]
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            expected={'sessions','events','messages','turns','tools','pins'} | ({'event_commits'} if version==DB_VERSION else set())
            if tables!=expected:raise StoreError('database_schema')
            db.execute('BEGIN')
            if version==DB_VERSION:
                self._verify_commits(db)
            counts={};message_count=0
            for row in db.execute('SELECT session_id,event_id,sequence,event_type,timestamp,payload,source,privacy_class,schema_version,canonical FROM events ORDER BY session_id,sequence'):
                sid,eid,seq,kind,stamp,payload,source,privacy,version,canonical=row
                counts[sid]=counts.get(sid,0)+1
                if seq!=counts[sid]:raise StoreError('event_sequence_invalid')
                event=Event(sid,eid,kind,stamp,json.loads(payload),source,privacy,version)
                if hashlib.sha256(event.canonical().encode()).hexdigest()!=canonical:raise StoreError('stored_event_invalid')
                if kind in ('user.message','assistant.message'):
                    message_count+=1
                    projected=db.execute('SELECT content FROM messages WHERE id=?',(eid,)).fetchone()
                    if projected is None or projected[0]!=event.payload['content']:raise StoreError('message_projection_invalid')
            if db.execute('SELECT count(*) FROM messages').fetchone()[0]!=message_count:raise StoreError('message_projection_invalid')
            for sid,seq in db.execute('SELECT id,seq FROM sessions'):
                if counts.get(sid,0)!=seq:raise StoreError('session_sequence_invalid')
        finally:db.close()

    @staticmethod
    def _verify_commits(db):
        for sid,seq in db.execute('SELECT id,seq FROM sessions'):
            last=0
            rows=db.execute('SELECT start_sequence,end_sequence FROM event_commits WHERE session_id=? ORDER BY end_sequence',(sid,)).fetchall()
            for start,end in rows:
                if not 1<=start<=end<=seq or (last and start!=last+1) or (not last and start!=1 and start!=end):
                    raise StoreError('commit_boundary_invalid')
                last=end
            if last!=seq:raise StoreError('commit_boundary_invalid')
        if db.execute('PRAGMA foreign_key_check').fetchone():raise StoreError('database_foreign_key')

    def _guard(self):
        try:self._check_path()
        except OSError:raise StoreError('storage_path_unavailable') from None

    def _check_path(self):
        if self._anchor is None:raise StoreError('store_closed')
        probe=Path('/')
        for part in self.path.parent.parts[1:]:
            probe/=part
            if probe.is_symlink():raise StoreError('storage_symlink')
        parent=self.path.parent.lstat();info=self.path.lstat()
        if (_identity(parent)!=self._parent_identity or parent.st_uid!=os.geteuid() or stat.S_IMODE(parent.st_mode)&0o077
            or _identity(info)!=self._db_identity or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
            or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)&0o077):raise StoreError('storage_metadata_changed')
        for suffix in ('-journal','-wal','-shm'):
            side=self.path.with_name(self.path.name+suffix)
            try:meta=side.lstat()
            except FileNotFoundError:continue
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=os.geteuid() or meta.st_nlink!=1 or stat.S_IMODE(meta.st_mode)&0o077:raise StoreError('unsafe_sqlite_sidecar')
        if info.st_size>self.limits['max_bytes']:raise StoreError('database_size_limit')

    @contextmanager
    def connection(self):
        self._guard();db=None
        try:
            db=sqlite3.connect(str(self.path),timeout=2,isolation_level=None)
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA secure_delete=ON');db.execute('PRAGMA temp_store=MEMORY')
            page=db.execute('PRAGMA page_size').fetchone()[0]
            db.execute('PRAGMA max_page_count='+str(self.limits['max_bytes']//page))
            self._guard()
            yield db
        except sqlite3.Error:
            raise StoreError('database_operation_failed') from None
        finally:
            if db is not None:db.close()

    def close(self):
        for field in ('_anchor','_db_fd'):
            fd=getattr(self,field,None)
            if fd is not None:os.close(fd);setattr(self,field,None)

    def __enter__(self):return self
    def __exit__(self,*exc):self.close()

    def _session(self,db,sid):
        row=db.execute('SELECT * FROM sessions WHERE id=? AND namespace=? AND workspace=?',(sid,self.namespace,self.workspace_ref)).fetchone()
        if row is None:raise StoreError('session_not_found')
        return row

    def create_session(self,title='新对话'):
        sid=identifier();self.append(Event.create(sid,'conversation.created',{'title':title[:80]}));return sid

    def append(self,event):return self.append_many([event])[0]

    def append_many(self,events):
        if not 1<=len(events)<=32:raise StoreError('event_batch_limit')
        prepared=[]
        for event in events:
            from .event_privacy import safe_text
            for key,value in event.payload.items():
                if type(value) is str and key in ('content','title') and safe_text(value,self.secrets,max_bytes=65536)[0]!=value:
                    raise StoreError('sensitive_or_oversized_event_text')
            canonical=hashlib.sha256(event.canonical().encode()).hexdigest()
            payload=json.dumps(event.payload,ensure_ascii=True,sort_keys=True,separators=(',',':'))
            if len(payload.encode())>self.limits['max_payload_bytes']:raise StoreError('event_payload_limit')
            prepared.append((event,canonical,payload))
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                seqs=[];new_sequences={}
                for event,canonical,payload in prepared:
                    old=db.execute('SELECT canonical,sequence FROM events WHERE event_id=?',(event.event_id,)).fetchone()
                    if old:
                        if old['canonical']!=canonical:raise StoreError('event_id_conflict')
                        self._session(db,event.session_id);seqs.append(old['sequence']);continue
                    if db.execute('SELECT count(*) FROM events').fetchone()[0]>=self.limits['max_events']:raise StoreError('event_count_limit')
                    if event.event_type=='conversation.created':
                        db.execute('INSERT INTO sessions(id,namespace,workspace,title,created) VALUES(?,?,?,?,?)',
                            (event.session_id,self.namespace,self.workspace_ref,event.payload['title'],event.timestamp))
                    s=self._session(db,event.session_id);seq=s['seq']+1
                    db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)',(event.session_id,event.event_id,seq,event.event_type,event.timestamp,payload,event.source,event.privacy_class,event.schema_version,canonical))
                    db.execute('UPDATE sessions SET seq=? WHERE id=?',(seq,event.session_id))
                    self._project(db,event,seq);seqs.append(seq)
                    new_sequences.setdefault(event.session_id,[]).append(seq)
                for sid in {e.session_id for e,_,_ in prepared}:
                    active=db.execute("SELECT content FROM pins WHERE session_id=? AND status='active'",(sid,)).fetchall()
                    if len(active)>12 or sum(len(r[0].encode('utf-8')) for r in active)>4096:raise StoreError('pin_active_budget')
                for sid,values in new_sequences.items():
                    db.execute('INSERT INTO event_commits VALUES(?,?,?)',(sid,min(values),max(values)))
                db.execute('COMMIT');return seqs
            except BaseException:
                db.execute('ROLLBACK');raise

    def _project(self,db,event,seq):
        p=event.payload;sid=event.session_id;kind=event.event_type
        if kind in ('user.message','assistant.message'):
            role='user' if kind=='user.message' else 'assistant'
            if role=='user':
                if db.execute("SELECT 1 FROM turns WHERE session_id=? AND state IN ('running','pending')",(sid,)).fetchone():raise StoreError('session_turn_busy')
                db.execute('INSERT INTO turns(id,session_id,user_id,state,sequence) VALUES(?,?,?,?,?)',(p['turn_id'],sid,event.event_id,'pending',seq))
                db.execute("UPDATE sessions SET title=CASE WHEN title='新对话' THEN ? ELSE title END WHERE id=?",(p['content'][:32],sid))
            else:self._turn(db,sid,p['turn_id'])
            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)',(event.event_id,sid,p['turn_id'],role,p['content'],int(p['truncated']),event.timestamp,seq))
        elif kind=='turn.started':
            self._turn(db,sid,p['turn_id'],'pending')
            if p['owner_pid']!=os.getpid():raise StoreError('turn_owner')
            if self._uncertain(db):raise StoreError('workspace_execution_uncertain')
            db.execute("UPDATE turns SET state='running',owner_pid=? WHERE id=?",(p['owner_pid'],p['turn_id']))
        elif kind in ('turn.finished','turn.interrupted'):
            turn=self._turn(db,sid,p['turn_id'])
            if turn['state'] not in ('running','pending'):raise StoreError('turn_already_terminal')
            status=p['status']
            if status not in STATUSES:raise StoreError('terminal_status')
            if kind=='turn.finished' and db.execute("SELECT 1 FROM tools WHERE turn_id=? AND state='started'",(p['turn_id'],)).fetchone():raise StoreError('unfinished_tools')
            if kind=='turn.finished' and not db.execute("SELECT 1 FROM messages WHERE turn_id=? AND role='assistant'",(p['turn_id'],)).fetchone():raise StoreError('final_message_missing')
            db.execute('UPDATE turns SET state=? WHERE id=?',(status,p['turn_id']))
        elif kind=='turn.reviewed':
            self._turn(db,sid,p['turn_id'],'execution_uncertain')
            db.execute("UPDATE turns SET state='interrupted' WHERE id=?",(p['turn_id'],))
            db.execute("UPDATE tools SET state='reviewed_unknown' WHERE turn_id=? AND state='started'",(p['turn_id'],))
        elif kind=='tool.started':
            self._turn(db,sid,p['turn_id'],'running')
            db.execute("INSERT INTO tools(id,turn_id,name,side_effect,state) VALUES(?,?,?,?,'started')",(p['tool_id'],p['turn_id'],p['name'],int(p['side_effect'])))
        elif kind=='tool.finished':
            self._turn(db,sid,p['turn_id'],'running')
            row=db.execute("SELECT * FROM tools WHERE id=? AND turn_id=? AND state='started'",(p['tool_id'],p['turn_id'])).fetchone()
            if row is None:raise StoreError('tool_not_started')
            db.execute('UPDATE tools SET state=?,effect=? WHERE id=?',('finished' if p['success'] else 'failed',p['effect'],p['tool_id']))
        elif kind=='context.cleared':db.execute('UPDATE sessions SET context_after=? WHERE id=?',(seq,sid))
        elif kind.startswith('pin.'):
            if db.execute("SELECT 1 FROM turns WHERE session_id=? AND state IN ('running','pending')",(sid,)).fetchone():raise StoreError('pin_while_running')
            self._pin(db,event)
        elif 'turn_id' in p:self._turn(db,sid,p['turn_id'],'running')

    @staticmethod
    def _turn(db,sid,tid,state=None):
        row=db.execute('SELECT * FROM turns WHERE id=? AND session_id=?',(tid,sid)).fetchone()
        if row is None or state is not None and row['state']!=state:raise StoreError('invalid_turn_transition')
        return row

    def _pin(self,db,event):
        p=event.payload;sid=event.session_id
        db.execute('UPDATE sessions SET pin_revision=pin_revision+1 WHERE id=?',(sid,))
        rev=self._session(db,sid)['pin_revision']
        if event.event_type=='pin.added':
            row=db.execute("SELECT content FROM messages WHERE id=? AND session_id=? AND role='user'",(p['source_message_id'],sid)).fetchone()
            if row is None or row['content'][p['start']:p['end']]!=p['content']:raise StoreError('pin_source_mismatch')
            if db.execute('SELECT count(*) FROM pins WHERE session_id=?',(sid,)).fetchone()[0]>=100:raise StoreError('pin_history_limit')
            db.execute("INSERT INTO pins VALUES(?,?,?,?,?,?,?,?,?,'active',NULL)",(p['pin_id'],sid,p['category'],p['content'],p['source_message_id'],p['start'],p['end'],event.timestamp,rev,))
        else:
            row=db.execute("SELECT * FROM pins WHERE id=? AND session_id=? AND status='active' AND revision=?",(p['pin_id'],sid,p['expected_revision'])).fetchone()
            if row is None:raise StoreError('pin_revision_conflict')
            if event.event_type=='pin.superseded':
                other=db.execute("SELECT 1 FROM pins WHERE id=? AND session_id=? AND status='active'",(p['new_pin_id'],sid)).fetchone()
                if other is None or p['new_pin_id']==p['pin_id']:raise StoreError('invalid_replacement')
            db.execute('UPDATE pins SET status=?,superseded_by=?,revision=? WHERE id=?',('superseded' if event.event_type=='pin.superseded' else 'revoked',p.get('new_pin_id'),rev,p['pin_id']))

    def _uncertain(self,db):
        return bool(db.execute("SELECT 1 FROM turns JOIN sessions ON sessions.id=turns.session_id WHERE sessions.workspace=? AND (state='execution_uncertain' OR state IN ('running','pending') AND EXISTS(SELECT 1 FROM tools WHERE tools.turn_id=turns.id AND tools.side_effect=1)) LIMIT 1",(self.workspace_ref,)).fetchone())

    def workspace_uncertain(self):
        with self.connection() as db:return self._uncertain(db)

    def query(self,sql,args=()):
        # Host-internal read projections only, never exposed to model or HTTP input.
        with self.connection() as db:
            if not sql.lstrip().upper().startswith('SELECT'):raise StoreError('read_query_only')
            return [dict(r) for r in db.execute(sql,args).fetchall()]

    def sessions(self,limit=20):
        if type(limit) is not int or not 1<=limit<=100:raise StoreError('list_limit')
        return self.query('SELECT * FROM sessions WHERE namespace=? AND workspace=? ORDER BY created DESC LIMIT ?', (self.namespace,self.workspace_ref,limit))

    def events(self,sid,*,after=0,limit=100):
        if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=200:raise StoreError('event_read_limit')
        with self.connection() as db:
            self._session(db,sid)
            rows=db.execute('SELECT * FROM events WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?',(sid,after,limit)).fetchall()
            result=[]
            for row in rows:
                item=dict(row);item['payload']=json.loads(item['payload'])
                e=Event(sid,item['event_id'],item['event_type'],item['timestamp'],item['payload'],item['source'],item['privacy_class'],item['schema_version'])
                if hashlib.sha256(e.canonical().encode()).hexdigest()!=item.pop('canonical'):raise StoreError('stored_event_invalid')
                result.append(item)
            return result

    def delete(self,sid):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                self._session(db,sid)
                if db.execute("SELECT 1 FROM turns WHERE session_id=? AND state IN ('running','pending','execution_uncertain')",(sid,)).fetchone():raise StoreError('unsafe_session_delete')
                db.execute('DELETE FROM sessions WHERE id=?',(sid,));db.execute('COMMIT')
            except BaseException:db.execute('ROLLBACK');raise


class MemoryEventStore(SessionEventStore):
    """Same transactional contracts, no disk or cross-restart guarantee."""
    def __init__(self,workspace,*,namespace='cli',secrets=(),settings=None):
        self.workspace=Path(workspace).resolve();self.namespace=namespace;self.secrets=tuple(secrets)
        self.workspace_ref=hashlib.sha256(os.fsencode(self.workspace)).hexdigest();self.limits=limits(settings)
        self.db=sqlite3.connect(':memory:',isolation_level=None);self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON');self.db.executescript(SCHEMA+COMMITS_SCHEMA)
        self.db.execute('PRAGMA max_page_count='+str(self.limits['max_bytes']//4096))
    @contextmanager
    def connection(self):
        if self.db is None:raise StoreError('store_closed')
        try:yield self.db
        except sqlite3.Error:raise StoreError('database_operation_failed') from None
    def close(self):
        if self.db is not None:self.db.close();self.db=None
