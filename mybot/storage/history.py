"""One channel/session owner. Commits facts before publication or tool dispatch."""
import os
from .event_schema import Event,StoreError,identifier
from .event_privacy import safe_text,configured_secrets
from .event_store import SessionEventStore,MemoryEventStore
from .projections import ConversationProjection,ModelContextProjection,TaskStatusProjection
from ..agent.pinned_context import PinnedContext


def open_store(config,channel):
    namespace=channel+':'+__import__('hashlib').sha256(os.fsencode(config.workspace.resolve())).hexdigest()[:16]
    cls=SessionEventStore if config.storage_backend=='event_sqlite' else MemoryEventStore
    kwargs=dict(namespace=namespace,secrets=configured_secrets(config),settings=config.session_event_limits)
    return cls(config.session_event_path,config.workspace,**kwargs) if cls is SessionEventStore else cls(config.workspace,**kwargs)


def alive(pid):
    if pid<=0:return False
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True


def recover(store):
    # Read first; no SQLite transaction is held while checking process liveness.
    rows=store.query("SELECT turns.* FROM turns JOIN sessions ON sessions.id=turns.session_id WHERE sessions.namespace=? AND sessions.workspace=? AND state IN ('pending','running')",(store.namespace,store.workspace_ref))
    recovered=[]
    for row in rows:
        if alive(row['owner_pid']):continue
        history=SessionHistory(store,row['session_id']);history.turn_id=row['id']
        try:history.interrupt('process_stopped');recovered.append(row['session_id'])
        except StoreError:
            # Another owner may have completed it between the read and append.
            if TaskStatusProjection(store,row['session_id']).current()['status'] in ('pending','running'):raise
    return recovered


class SessionHistory:
    def __init__(self,store,sid=None):
        self.store=store;self.sid=sid or store.create_session();self.turn_id=None
        self.pins=PinnedContext(store,self.sid)

    def event(self,kind,payload,**kw):return self.store.append(Event.create(self.sid,kind,payload,**kw))

    def start(self,text):
        if self.turn_id is not None:raise StoreError('history_turn_busy')
        tid=identifier();content,truncated=safe_text(text,self.store.secrets)
        user=Event.create(self.sid,'user.message',dict(turn_id=tid,content=content,truncated=truncated),source='user',privacy_class='chat')
        started=Event.create(self.sid,'turn.started',dict(turn_id=tid,owner_pid=os.getpid()))
        self.store.append_many([user,started]);self.turn_id=tid
        return user.event_id

    def finish(self,text,status='completed'):
        if self.turn_id is None:raise StoreError('no_active_turn')
        content,truncated=safe_text(text,self.store.secrets)
        self.store.append_many([Event.create(self.sid,'assistant.message',dict(turn_id=self.turn_id,content=content,truncated=truncated),source='host',privacy_class='chat'),
            Event.create(self.sid,'turn.finished',dict(turn_id=self.turn_id,status=status))])
        self.turn_id=None

    def interrupt(self,reason='runtime_failed',*,cancelled=False,failed=False,force_uncertain=False):
        if self.turn_id is None:return
        tools=self.store.query('SELECT side_effect,state,effect FROM tools WHERE turn_id=?',(self.turn_id,))
        uncertain=force_uncertain or any(r['side_effect'] and (r['state']=='started' or r['effect'] in ('possible','changed')) for r in tools)
        status='execution_uncertain' if uncertain else 'cancelled' if cancelled else 'failed' if failed else 'interrupted'
        self.event('turn.interrupted',dict(turn_id=self.turn_id,status=status,reason=reason),source='recovery' if reason=='process_stopped' else 'host')
        self.turn_id=None

    def review(self,*,confirmed=False):
        if confirmed is not True:raise StoreError('review_confirmation_required')
        status=TaskStatusProjection(self.store,self.sid).current()
        self.event('turn.reviewed',dict(turn_id=status['turn_id']),source='user_confirmed')

    def clear_context(self):self.event('context.cleared',{})
    def title(self):
        with self.store.connection() as db:return self.store._session(db,self.sid)['title']
    def messages(self,**kwargs):return ConversationProjection(self.store,self.sid).messages(**kwargs)
    def context_turns(self,turns):
        # Retain canonical facts. Omit complete historical protocol groups containing
        # withdrawn pin text rather than inventing tool results or stitched quotes.
        obsolete=[p['content'] for p in self.pins.list() if p['status']!='active']
        if not obsolete:return turns
        import json
        def contains(value):
            if isinstance(value,str):
                if any(text in value for text in obsolete):return True
                try:decoded=json.loads(value)
                except (ValueError,RecursionError):return False
                return contains(decoded) if not isinstance(decoded,str) else False
            if isinstance(value,dict):return any(contains(v) for v in value.values())
            if isinstance(value,list):return any(contains(v) for v in value)
            return False
        return [turn for turn in turns if not contains(turn)]

    def model_turns(self,limit=6):return ModelContextProjection(self.store,self.sid).turns(limit)
    def status(self):return TaskStatusProjection(self.store,self.sid).current()

    def begin(self,name,params,tool,capability):
        if self.turn_id is None:return None
        side=capability in ('workspace_mutation','command_execution','external_side_effect')
        from ..tools.patch import ApplyPatchTool
        from ..tools.run_command import RunCommandTool
        if type(tool) is ApplyPatchTool and (params.get('dry_run',True) is True or tool.patch_mode=='preview'):side=False
        if type(tool) is RunCommandTool and tool.settings.mode=='macos_readonly':side=False
        tool_id=identifier()
        self.event('tool.started',dict(turn_id=self.turn_id,tool_id=tool_id,name=name,side_effect=side))
        return tool_id,side

    def complete(self,token,result):
        if token is None:return
        tool_id,side=token
        effect='changed' if side and result.metadata.get('applied') else 'possible' if side and (
            not (result.metadata.get('executed') is False or result.metadata.get('approved') is False or result.metadata.get('status')=='preflight_failed')) else 'none'
        self.event('tool.finished',dict(turn_id=self.turn_id,tool_id=tool_id,success=bool(result.success),effect=effect))
