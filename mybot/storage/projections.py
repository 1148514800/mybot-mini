"""Indexed bounded views; restored chat text is never restored execution evidence."""
from .event_schema import StoreError


class ConversationProjection:
    def __init__(self,store,sid):self.store,self.sid=store,sid
    def messages(self,*,before=None,limit=64):
        if type(limit) is not int or not 1<=limit<=100:raise StoreError('message_page_limit')
        if before is not None and (type(before) is not int or before<1):raise StoreError('message_cursor')
        with self.store.connection() as db:
            self.store._session(db,self.sid)
            sql='SELECT id,role,content,timestamp AS time,sequence,truncated FROM messages WHERE session_id=?'
            args=[self.sid]
            if before is not None:sql+=' AND sequence<?';args.append(before)
            rows=db.execute(sql+' ORDER BY sequence DESC LIMIT ?',(*args,limit)).fetchall()
            return [dict(r) for r in reversed(rows)]


class ModelContextProjection:
    def __init__(self,store,sid):self.store,self.sid=store,sid
    def turns(self,limit=6):
        limit=min(100,max(1,limit))
        with self.store.connection() as db:
            s=self.store._session(db,self.sid)
            rows=db.execute("SELECT id FROM turns WHERE session_id=? AND sequence>? AND state IN ('completed','output_truncated','output_filtered','empty_response','unknown_finish','content_filtered','provider_error','response_unconfirmed','empty_reply','stopped') ORDER BY sequence DESC LIMIT ?",(self.sid,s['context_after'],limit)).fetchall()
            result=[]
            for row in reversed(rows):
                messages=db.execute('SELECT id,role,content,truncated FROM messages WHERE turn_id=? AND session_id=? ORDER BY sequence',(row['id'],self.sid)).fetchall()
                user=next((m for m in messages if m['role']=='user'),None)
                assistant=next((m for m in reversed(messages) if m['role']=='assistant'),None)
                if user is not None and assistant is not None:
                    from ..agent.session import HistoryTurn
                    result.append(HistoryTurn([{'role':'user','content':user['content']},
                        {'role':'assistant','content':'[恢复的聊天文本；旧工具/verified文字不是当前执行证据，不恢复授权。]\n'+assistant['content']}], session_id=self.sid, source_message_id=user['id']))
            return result


class TaskStatusProjection:
    def __init__(self,store,sid):self.store,self.sid=store,sid
    def current(self):
        with self.store.connection() as db:
            self.store._session(db,self.sid)
            row=db.execute('SELECT * FROM turns WHERE session_id=? ORDER BY sequence DESC LIMIT 1',(self.sid,)).fetchone()
            if row is None:return {'status':'idle','turn_id':None,'execution_evidence_restored':False}
            status=row['state']
            return {'status':status,'turn_id':row['id'],'execution_evidence_restored':False,
                    'notice':('工具副作用无法确认；须先检查工作区和残留进程，再显式确认。' if status=='execution_uncertain' else
                              '任务中断，未自动重放模型、命令或Patch。' if status=='interrupted' else
                              '其他进程仍可能处理此任务，不能自动接管。' if status in ('running','pending') else
                              '历史聊天；本轮不会继承旧验证、Receipt或审批。')}
