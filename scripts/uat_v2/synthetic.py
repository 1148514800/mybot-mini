"""Only for disposable offline rehearsal; reference edits never reach Live clients."""
import json
import re
from scripts.check_session import response,call
from .calibrate import cited_response
from mybot.agent.context_compactor import PROMPT
from mybot.tools.patch import sha

FIXES={
'T01':{'src/tag_shelf.py':'''def normalize_tags(tags):
    seen = set()
    result = []
    for raw in tags:
        text = raw.strip()
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            result.append(text)
    return result
'''},
'T02':{
 'src/parcel_totals/calculations.py':'''from decimal import Decimal, ROUND_HALF_UP

def line_subtotal(line):
    if type(line.quantity) is not int or line.quantity < 0:
        raise ValueError('quantity must be a nonnegative integer')
    result = (line.unit_price * line.quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return abs(result) if result == 0 else result
''',
 'src/parcel_totals/service.py':'''from decimal import Decimal
from .calculations import line_subtotal

def summarize_order(lines):
    rows = []
    total = Decimal('0.00')
    for line in lines:
        subtotal = line_subtotal(line)
        rows.append({'sku': line.sku, 'quantity': line.quantity, 'subtotal': format(subtotal, '.2f')})
        total += subtotal
    return {'lines': rows, 'total': format(total, '.2f')}
'''}}


class SyntheticClient:
    def __init__(self,config,case):
        from types import SimpleNamespace as N
        self.config=config;self.case=case;self.step=0;self.requests=[]
        self.chat=N(completions=N(create=self.create))
    async def create(self,**request):
        self.requests.append(request)
        if request['messages'][0]['content']==PROMPT:return cited_response(request)
        if self.case=='T03':return response('OFFLINE/SYNTHETIC：仅确认设计，尚未实现代码或运行测试，没有修改文件。')
        step=self.step;self.step+=1
        paths=list(FIXES[self.case])
        if step==0:return response(calls=[call('read-'+str(i),'read_file_range',json.dumps(dict(path=p,start_line=1,end_line=150))) for i,p in enumerate(paths)])
        if step==1:
            changes=[]
            for name,text in FIXES[self.case].items():
                data=(self.config.workspace/name).read_bytes()
                changes.append(dict(op='update',path=name,expected_sha256=sha(data),edits=[dict(old_text=data.decode(),new_text=text)]))
            return response(calls=[call('preview','apply_patch',json.dumps(dict(dry_run=True,changes=changes)))])
        if step==2:
            # Native context clipping may make the metadata JSON partial while
            # keeping the complete receipt visible. Read only that visible field;
            # never fetch a capability from host state or construct a new one.
            match=re.search(r'"preview_receipt":\s*"([a-f0-9]{64})"',request['messages'][-1]['content'])
            if match is None:raise RuntimeError('synthetic_visible_receipt_missing')
            return response(calls=[call('commit','apply_patch',json.dumps(dict(dry_run=False,preview_receipt=match.group(1))))])
        if step==3:return response(calls=[call('unit','run_command',json.dumps(dict(argv=['python','-m','unittest','discover','-s','tests','-v'])))])
        return response('OFFLINE/SYNTHETIC：合成流程结束，不是真实模型能力结论。')
    async def close(self):pass
