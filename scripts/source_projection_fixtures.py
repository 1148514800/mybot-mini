"""New synthetic fixtures derived only from public L02 product units; no Live DB."""
from copy import deepcopy
from pathlib import Path
from mybot.storage.history import SessionHistory,open_store
from mybot.agent.session import HistoryTurn
from scripts.eventstore_fixtures import configuration,SyntheticClient

OLD='索引文件命名为 index.md。'
NEW='索引文件改为 catalog.md。'
UNITS=['列表默认每页显示20条。','搜索结果按相对路径排序。','空目录显示空状态说明。','界面第一版只需中文。','索引条目展示相对路径。']
FIRST=OLD+''.join(UNITS[:3]);SECOND=NEW+''.join(UNITS[3:])


def stored(history,text,reply='历史建议，尚未实现。'):
    mid=history.start(text);turn=history.identify_turn([{'role':'user','content':text},{'role':'assistant','content':reply}]);history.finish(reply)
    return mid,turn


def pin(history,mid,text,offset=0,**kw):
    source=next(m for m in history.messages(limit=100) if m['id']==mid);start=source['content'].index(text,offset)
    ident=history.pins.add(mid,start,start+len(text),'user_constraint',confirmed=True,**kw)
    return next(p for p in history.pins.list() if p['id']==ident)


def revoke(history,p):history.pins.revoke(p['id'],p['revision'],confirmed=True)


def source_fixture(root):
    cfg=configuration(Path(root).resolve(),context_max_chars=40000,context_recent_turns=6,context_token_budget={'mode':'estimate','input_limit':20000})
    store=open_store(cfg,'cli');h=SessionHistory(store)
    m1,t1=stored(h,FIRST,OLD+'这是助手复述，不是独立确认。');old=pin(h,m1,OLD)
    m2,t2=stored(h,SECOND,'建议以新规则为准，其他设计未实现。');new=pin(h,m2,NEW,replace_id=old['id'],expected_revision=old['revision'])
    return cfg,store,h,[t1,t2],new


def baseline_projection(turns,obsolete):
    # Public baseline's complete-turn containment rule, isolated synthetic data.
    import json
    return [deepcopy(t) for t in turns if not any(x in json.dumps(t,ensure_ascii=False) for x in obsolete)]
