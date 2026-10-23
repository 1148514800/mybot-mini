"""Host-only independent acceptance assertions. Never copy into model workspaces."""
HIDDEN={
'T01':'''import sys
sys.path.insert(0,sys.argv[1]+'/src')
from tag_shelf import normalize_tags
samples=[([],[]),(['  ','\\t','\\u2003'],[]),(['Beta','alpha','BETA',' Gamma ','ALPHA'],['Beta','alpha','Gamma']),(['Straße','STRASSE','中文',' 中文 '],['Straße','中文'])]
for tags,expected in samples:
 before=list(tags);result=normalize_tags(tags)
 assert result==expected and tags==before and result is not tags
print('independent tags assertions PASS')
''',
'T02':'''import sys
sys.path.insert(0,sys.argv[1]+'/src')
from decimal import Decimal
from parcel_totals import OrderLine,summarize_order
from parcel_totals.calculations import line_subtotal
rows=[OrderLine('same',3,Decimal('0.335')),OrderLine('same',1,Decimal('-1.005')),OrderLine('zero',0,Decimal('9.7'))]
before=list(rows)
assert summarize_order(rows)=={'lines':[{'sku':'same','quantity':3,'subtotal':'1.01'},{'sku':'same','quantity':1,'subtotal':'-1.01'},{'sku':'zero','quantity':0,'subtotal':'0.00'}],'total':'0.00'}
assert rows==before
assert summarize_order([])=={'lines':[],'total':'0.00'}
assert summarize_order([OrderLine('zero-negative',0,Decimal('-2'))])['lines'][0]['subtotal']=='0.00'
assert summarize_order([OrderLine('a',1,Decimal('0.005')),OrderLine('b',1,Decimal('0.005'))])['total']=='0.02'
for qty in (-1,True,False,1.5):
 for fn in (line_subtotal,lambda x:summarize_order([x])):
  try:fn(OrderLine('invalid',qty,Decimal('2')))
  except ValueError:pass
  else:raise AssertionError('quantity contract')
# Observe the actual helper code frame; do not constrain import/alias style.
calls=[]
def observe(frame,event,arg):
 if event=='call' and frame.f_code is line_subtotal.__code__:calls.append(True)
sys.setprofile(observe)
try:result=summarize_order([OrderLine('probe',2,Decimal('1.23'))])
finally:sys.setprofile(None)
assert calls and result['total']=='2.46'
print('independent totals assertions PASS')
'''}


async def assess(case,root,*,hidden=True):
    import os,tempfile
    from pathlib import Path
    from mybot.tools.command_process import trusted_python,Launch,run_process
    from mybot.tools.macos_sandbox import profile,verify_sandbox
    executable,roots,versions=trusted_python(root)
    if not await verify_sandbox(roots):raise RuntimeError('independent_sandbox_unavailable')
    argv=(str(executable),'-I','-B','-c',HIDDEN[case],str(root)) if hidden else (str(executable),'-I','-B','-m','unittest','discover','-s','tests','-v')
    with tempfile.TemporaryDirectory(prefix='uat-v2-host-oracle-') as folder:
        temp=Path(folder).resolve();fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:result=await run_process(Launch(argv,roots,versions),cwd=root,cwd_fd=fd,temp=temp,timeout=30,output_limit=10000,profile=profile(root,temp,roots))
        finally:os.close(fd)
    return dict(passed=result.exit_code==0 and result.status=='completed',returncode=result.exit_code,
                status=result.status,sandbox_applied=result.sandbox_applied,
                stdout=result.stdout.decode(errors='replace'),stderr=result.stderr.decode(errors='replace'))
