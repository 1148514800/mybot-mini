"""Disposable public projects and independent host-only acceptance contracts."""
import hashlib,json,subprocess,sys
from pathlib import Path

COMMON={
 'pyproject.toml':'[project]\nname="uat-fixture"\nversion="0.1.0"\nrequires-python=">=3.12"\n',
 '.gitignore':'__pycache__/\n*.pyc\n',
}
PROJECTS={
'U03':{
 'README.md':'# Order Desk\nSmall standard-library order service. Sources are under src/orderdesk; tests use unittest.\n',
 'src/orderdesk/__init__.py':'',
 'src/orderdesk/models.py':'from dataclasses import dataclass\nfrom decimal import Decimal\n\n@dataclass(frozen=True)\nclass Item:\n    unit_price: Decimal\n    quantity: int\n',
 'src/orderdesk/money.py':'from decimal import Decimal, ROUND_HALF_UP\n\ndef cents(value):\n    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)\n',
 'src/orderdesk/pricing.py':'from .money import cents\n\ndef line_total(item):\n    if type(item.quantity) is not int or item.quantity < 0:\n        raise ValueError("quantity must be a nonnegative integer")\n    return cents(item.unit_price * item.quantity)\n',
 'src/orderdesk/service.py':'from decimal import Decimal\nfrom .models import Item\nfrom .pricing import line_total\n\ndef order_total(items):\n    return sum((line_total(item) for item in items), Decimal("0.00"))\n',
 'tests/test_orders.py':'import sys,unittest\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))\nfrom decimal import Decimal\nfrom orderdesk.models import Item\nfrom orderdesk.service import order_total\nclass Orders(unittest.TestCase):\n def test_total(self):self.assertEqual(order_total([Item(Decimal("2.345"),2)]),Decimal("4.69"))\n',
},
'U04':{
 'README.md':'# Clock Cache\nA deterministic TTL cache with an injectable clock. Run python -m unittest discover -s tests -v. No external dependencies.\n',
 'src/clockcache/__init__.py':'from .cache import Cache\n',
 'src/clockcache/cache.py':'''import time

class Cache:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.entries = {}

    def set(self, key, value, ttl):
        self.entries[key] = (value, self.clock() + ttl)

    def get(self, key, default=None):
        if key not in self.entries:
            return default
        value, expires_at = self.entries[key]
        if self.clock() > expires_at:
            del self.entries[key]
            return default
        return value
''',
 'tests/test_cache.py':'''import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from clockcache import Cache
class CacheTests(unittest.TestCase):
 def setUp(self):self.now=10.0;self.cache=Cache(lambda:self.now)
 def test_before_expiry(self):
  self.cache.set('x','v',2);self.now=11.99;self.assertEqual(self.cache.get('x'),'v')
 def test_exact_expiry(self):
  self.cache.set('x','v',2);self.now=12.0;self.assertIsNone(self.cache.get('x'))
 def test_missing_default(self):self.assertEqual(self.cache.get('missing','fallback'),'fallback')
''',
},
'U05':{
 'README.md':'# Orders Export\nOrder models, business facade and CSV helpers. Standard library only. Public tests: python -m unittest discover -s tests -v.\n',
 'src/orderexport/__init__.py':'from .business import export_orders\nfrom .models import Order\n',
 'src/orderexport/models.py':'''from dataclasses import dataclass
from decimal import Decimal
@dataclass(frozen=True)
class Order:
    id: str
    name: str
    amount: Decimal
''',
 'src/orderexport/csv_export.py':'''def export_rows(orders):
    lines = ['id,name,amount']
    for order in orders:
        lines.append(f'{order.id},{order.name},{order.amount}')
    return '\\n'.join(lines) + '\\n'
''',
 'src/orderexport/business.py':'''from .models import Order
from .csv_export import export_rows

def export_orders(orders):
    # Existing legacy facade; helper integration is incomplete.
    return 'id,name\\n' + ''.join(f'{o.id},{o.name}\\n' for o in orders)
''',
 'tests/test_export.py':'''import csv,io,sys,unittest
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from orderexport import Order,export_orders
from orderexport.csv_export import export_rows
class Exports(unittest.TestCase):
 def test_header(self):self.assertEqual(next(csv.reader(io.StringIO(export_orders([])))),['id','name','amount'])
 def test_business_amount(self):
  rows=list(csv.reader(io.StringIO(export_orders([Order('1','Coffee',Decimal('2'))]))))
  self.assertEqual(rows,[['id','name','amount'],['1','Coffee','2.00']])
 def test_helper_quoting(self):
  rows=list(csv.reader(io.StringIO(export_rows([Order('2','A,"B"\\nC',Decimal('3.5'))]))))
  self.assertEqual(rows[1],['2','A,"B"\\nC','3.50'])
''',
}}
ALLOWED={'U03':[], 'U04':['src/clockcache/cache.py'],
         'U05':['src/orderexport/models.py','src/orderexport/csv_export.py','src/orderexport/business.py']}
# Host-only gold: never copied to a model workspace or inserted into model messages.
GOLD_U03={'entry':'orderdesk.service.order_total','paths':['src/orderdesk/service.py','src/orderdesk/pricing.py','src/orderdesk/money.py','src/orderdesk/models.py'],
 'facts':['line_total per item','quantity int and nonnegative','price times quantity','Decimal quantize 0.01 ROUND_HALF_UP per line','sum starts Decimal 0.00']}

HIDDEN={
'U04':'''import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
from clockcache import Cache
now=[100.0];c=Cache(lambda:now[0]);c.set('a',object(),5)
assert c.get('a') is not None
now[0]=105.0;assert c.get('a','expired')=='expired'
assert 'a' not in c.entries
c.set('zero','z',0);assert c.get('zero') is None
c.set('negative','n',-1);assert c.get('negative') is None
c.set('b','new',2);now[0]=106.999;assert c.get('b')=='new'
now[0]=107.0;assert c.get('b') is None
print('independent assertions PASS')
''',
'U05':'''import sys,csv,io
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
from orderexport import Order,export_orders
from orderexport.csv_export import export_rows
orders=[Order('a','comma,name',Decimal('12')),Order('b','say "hi"',Decimal('0.5')),Order('c','line1\\nline2',Decimal('-3.25')),Order('d','中文',Decimal('1.234'))]
expected=[['id','name','amount'],['a','comma,name','12.00'],['b','say "hi"','0.50'],['c','line1\\nline2','-3.25'],['d','中文','1.23']]
for fn in (export_orders,export_rows):
 text=fn(orders);assert isinstance(text,str)
 assert list(csv.reader(io.StringIO(text)))==expected
 assert list(csv.reader(io.StringIO(fn([]))))==[['id','name','amount']]
assert orders[0].name=='comma,name'
print('independent assertions PASS')
'''}

def fingerprint(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and not p.name.startswith('._')}

def create(case,root, *, _supported_metadata=False):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=False)
    if _supported_metadata:
        import os
        os.chown(root, -1, os.getegid())
    files={**COMMON,**PROJECTS.get(case,{'README.md':'# Disposable UAT notes\nNo code changes requested.\n'})}
    for name,text in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    if case not in ('U03','U04','U05'):
        from mybot.workspace import init_workspace
        init_workspace(root)
    subprocess.run(['git','init','-q',str(root)],check=True)
    subprocess.run(['git','-C',str(root),'add','.'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=UAT Fixture','-c','user.email=uat@example.invalid','-c','commit.gpgsign=false','commit','-qm','frozen fixture'],check=True)
    return fingerprint(root)

async def assess(case,root,*,hidden=True):
    import os,tempfile
    from mybot.tools.command_process import trusted_python,Launch,run_process
    from mybot.tools.macos_sandbox import profile,verify_sandbox
    if hidden and case not in HIDDEN:return None
    executable,roots,versions=trusted_python(root)
    if not await verify_sandbox(roots):raise RuntimeError('independent_sandbox_unavailable')
    argv=(str(executable),'-I','-B','-c',HIDDEN[case],str(root)) if hidden else (str(executable),'-I','-B','-m','unittest','discover','-s','tests','-v')
    launch=Launch(argv,roots,versions)
    with tempfile.TemporaryDirectory(prefix='uat-oracle-') as folder:
        temp=Path(folder).resolve();fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:result=await run_process(launch,cwd=root,cwd_fd=fd,temp=temp,timeout=20,output_limit=8000,profile=profile(root,temp,roots))
        finally:os.close(fd)
    return {'passed':result.exit_code==0 and result.status=='completed','returncode':result.exit_code,
            'status':result.status,'sandbox_applied':result.sandbox_applied,
            'stdout':result.stdout.decode(errors='replace')[:1000],
            'stderr':result.stderr.decode(errors='replace')[:6000]}


def changes(root,before):
    after=fingerprint(root)
    return sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k))


def create_v2(case, root):
    """New disposable version only; set root group before creating descendants.

    Never repairs or normalizes existing frozen fixtures. Product policy unchanged.
    """
    return create(case, root, _supported_metadata=True)
