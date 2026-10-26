"""Read-only quote evidence, not a semantic entailment classifier or model Tool.

A verified quote establishes attribution only. Pin confirmation applies to that
exact quote and host-selected category, never to a model's paraphrase.
"""
from ..storage.event_schema import StoreError

KINDS=('user_statement','host_confirmed_pin','user_optional_proposal','user_unresolved_question',
       'assistant_suggestion','assistant_unconfirmed_inference')
NOTICE=('仅固定原文及其用户选择的用途获得确认；普通原文的可选、未决含义不由宿主猜测。'
        '模型回答、建议和推断不是已确认事项；原文可核验不代表更强改写成立。')


def quote_evidence(db,sid,message_id,span,quote):
    if (type(span) not in (list,tuple) or len(span)!=2 or any(type(n) is not int for n in span)
        or type(quote) is not str):raise StoreError('decision_source_span')
    row=db.execute('SELECT * FROM messages WHERE id=? AND session_id=?',(message_id,sid)).fetchone()
    a,b=span
    if row is None or row['role']!='user':raise StoreError('decision_user_source_required')
    if row['truncated'] or any(m in row['content'] for m in ('[已隐藏]','[本地路径已隐藏]','[摘要已隐藏]')):
        raise StoreError('decision_source_incomplete')
    if not 0<=a<b<=len(row['content']) or row['content'][a:b]!=quote:raise StoreError('decision_quote_mismatch')
    return dict(session_id=sid,source_message_id=message_id,source_span=[a,b],source_role='user',original_quote=quote,
        provenance_kind='user_statement',semantic_classification='unclassified',confirmation_event_id=None,
        confirmation_event_sequence=None,current_lifecycle_status='not_pinned')


class DecisionProvenance:
    def __init__(self,store,sid):self.store,self.sid=store,sid
    def statement(self,message_id,span,quote):
        with self.store.connection() as db:
            self.store._session(db,self.sid)
            return quote_evidence(db,self.sid,message_id,span,quote)
    def view(self,*,boundary=None,limit=100):
        from ..storage.decision_timeline import DecisionTimeline
        return DecisionTimeline(self.store,self.sid).view(boundary=boundary,limit=limit)


def classification_proposal(text,kind):
    # Model classification is explicitly not a confirmation or a new event.
    if type(text) is not str or not 1<=len(text)<=512 or kind not in KINDS or kind=='host_confirmed_pin':
        raise StoreError('decision_proposal_invalid')
    return dict(text=text,proposed_kind=kind,verified=False,user_confirmed=False,execution_authority=False)


def render_view(view):
    """Shared CLI/Web wording; quotes remain data, not execution permissions."""
    lines=[NOTICE,'历史生效区间按已提交事件顺序计算；后来失效不表示当时错误。']
    if view['boundary']!=view['current_boundary']:lines.append(f"查询历史提交顺序 {view['boundary']}；当前顺序 {view['current_boundary']}。")
    for p in view['items']:
        status={'active':'当前有效','revoked':'历史曾有效，已撤销','superseded':'历史曾有效，已被替换'}[p['status_at_boundary']]
        if p['status_at_boundary']=='active' and view['boundary']!=view['current_boundary']:status='该历史边界有效'
        if p['ever_effective'] is False:status='已失效；同一提交内无可观察的生效区间'
        elif p['ever_effective'] is None and p['status_at_boundary']!='active':status='历史确认记录已失效，旧生效边界未知'
        start=p['valid_from'];end=p['valid_until']
        end_label=str(end) if end is not None else '旧边界未知' if p['ended_sequence'] is not None else '未失效'
        lines.append(f"{status}：{p['original_quote'] if p['source_verified'] else '来源不完整，未列入可信原文'}（生效顺序 {start if start is not None else '旧记录边界未知'}；失效顺序 {end_label}）")
    if view['omitted']:lines.append(f"另有 {view['omitted']} 项未展示；不能视为不存在。")
    return '\n'.join(lines)
