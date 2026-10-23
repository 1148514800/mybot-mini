"""Public new projects. Hidden contracts live outside each agent workspace."""
import os
from pathlib import Path
import subprocess
from scripts.uat.fixtures import COMMON, fingerprint

PROJECTS={
'T01':{
 'README.md':'''# Tag Shelf
Public interface: normalize_tags(tags) in src/tag_shelf.py.
Input is a list of strings. Apply Python str.strip(), drop whitespace-only items,
deduplicate using Unicode str.casefold() of the stripped text. Keep the first
stripped spelling and input order. Return a new list; never modify the input.
All-whitespace and empty lists return []. Other input types are outside this task.
No dependencies or network. Only src/tag_shelf.py may change.
Run: python -m unittest discover -s tests -v
''',
 'src/tag_shelf.py':'''def normalize_tags(tags):
    """Return unique tags for display, preserving the public list interface."""
    return sorted(set(tags))
''',
 'tests/test_tags.py':'''import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from tag_shelf import normalize_tags
class Tags(unittest.TestCase):
 def test_normal(self):self.assertEqual(normalize_tags(['Blue','Green']),['Blue','Green'])
 def test_whitespace_case_order(self):self.assertEqual(normalize_tags([' z ','A','Z',' a ','']),['z','A'])
 def test_input_unchanged(self):
  tags=[' A ','a'];before=list(tags);result=normalize_tags(tags)
  self.assertEqual(tags,before);self.assertIsNot(result,tags)
''',
},
'T02':{
 'README.md':'''# Parcel Totals
Public API: OrderLine(sku, quantity, unit_price) and summarize_order(lines).
Use only Python standard library, Decimal inputs and no external network.
quantity must have type(quantity) is int, >=0; bool, float and negative quantities
raise ValueError both at calculations.line_subtotal and the service entry point.
unit_price is a finite Decimal (negative prices allowed); SKU is a string.
For each line multiply quantity by unit_price then quantize Decimal('0.01') using
ROUND_HALF_UP. Sum these rounded subtotals, NOT raw products. Zero quantity gives
'0.00'; empty input gives {'lines': [], 'total': '0.00'}.
Return {'lines': [{'sku': original_sku, 'quantity': original_quantity,
'subtotal': 'fixed two decimals'}, ...], 'total': 'fixed two decimals'}.
Keep line order and duplicate SKUs, do not mutate the input list or OrderLine
objects, do not merge lines. The real service must call calculations.line_subtotal;
fixing only a helper while bypassing it at the entry is insufficient.
Only src/parcel_totals/calculations.py and src/parcel_totals/service.py may change.
Run: python -m unittest discover -s tests -v
''',
 'src/parcel_totals/__init__.py':'from .models import OrderLine\nfrom .service import summarize_order\n',
 'src/parcel_totals/models.py':'''from dataclasses import dataclass
from decimal import Decimal
@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price: Decimal
''',
 'src/parcel_totals/calculations.py':'''from decimal import Decimal

def line_subtotal(line):
    return (line.unit_price * line.quantity).quantize(Decimal('0.01'))
''',
 'src/parcel_totals/service.py':'''def summarize_order(lines):
    # Legacy entry still bypasses the calculation module.
    rows = [{'sku': x.sku, 'quantity': x.quantity,
             'subtotal': str(x.unit_price * x.quantity)} for x in lines]
    return {'lines': rows, 'total': str(sum(x.unit_price * x.quantity for x in lines))}
''',
 'tests/test_totals.py':'''import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from decimal import Decimal
from parcel_totals import OrderLine,summarize_order
from parcel_totals.calculations import line_subtotal
class Totals(unittest.TestCase):
 def test_helper_normal(self):self.assertEqual(line_subtotal(OrderLine('a',2,Decimal('1.20'))),Decimal('2.40'))
 def test_entry_rounding(self):
  rows=[OrderLine('a',1,Decimal('0.005')),OrderLine('b',1,Decimal('0.005'))]
  self.assertEqual(summarize_order(rows),{'lines':[{'sku':'a','quantity':1,'subtotal':'0.01'},{'sku':'b','quantity':1,'subtotal':'0.01'}],'total':'0.02'})
 def test_empty(self):self.assertEqual(summarize_order([]),{'lines':[],'total':'0.00'})
 def test_bool_rejected(self):
  with self.assertRaises(ValueError):summarize_order([OrderLine('a',True,Decimal('2'))])
''',
},
'T03':{'README.md':'# Offline Photo Organizer\nDesign discussion only. No code or file modifications authorized.\n'}
}
ALLOWED={'T01':['src/tag_shelf.py'], 'T02':['src/parcel_totals/calculations.py','src/parcel_totals/service.py'], 'T03':[]}


def create(case, root):
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=False)
    os.chown(root,-1,os.getegid())
    for name,text in {**COMMON,**PROJECTS[case]}.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    if case=='T03':
        from mybot.workspace import init_workspace
        init_workspace(root)
    subprocess.run(['git','init','-q',str(root)],check=True)
    subprocess.run(['git','-C',str(root),'add','.'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Targeted UAT v2','-c','user.email=uat-v2@example.invalid',
                    '-c','commit.gpgsign=false','commit','-qm','initial public fixture'],check=True)
    return fingerprint(root)
