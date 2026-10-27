"""Fixed public CSV contract and independent host suites; no host candidate import."""
import hashlib,os
from pathlib import Path
from mybot.evaluation.coding_fixtures import Image,write_images
from scripts.coding_workflow_canary_v1.fixture import git
from .plan import ALLOWED
BUG_PARSER='''def parse_records(csv_text):
    return [dict(id=row.split(',')[0], category=row.split(',')[1], amount=float(row.split(',')[2]))
            for row in csv_text.splitlines()[1:] if row]
'''
BUG_REPORT='''def category_totals(csv_text):
    rows = [line.split(',') for line in csv_text.splitlines()[1:] if line]
    return sorted({(row[1], str(float(row[2]))) for row in rows})
'''
REFERENCE_PARSER='''import csv
import io
import re
from decimal import Decimal

def parse_records(csv_text):
    records = []
    try:
        reader = csv.DictReader(io.StringIO(csv_text, newline=''), strict=True)
        if reader.fieldnames != ['id', 'category', 'amount']:
            raise ValueError('invalid header')
        for row in reader:
            if set(row) != {'id', 'category', 'amount'} or any(v is None for v in row.values()):
                raise ValueError('invalid fields')
            text = row['amount'].strip()
            if re.fullmatch(r'[+-]?(?:[0-9]+(?:\\.[0-9]{0,2})?|\\.[0-9]{1,2})', text) is None:
                raise ValueError('invalid amount')
            amount = Decimal(text)
            if not amount.is_finite():
                raise ValueError('nonfinite amount')
            records.append(dict(id=row['id'], category=row['category'].strip(), amount=amount))
    except csv.Error as error:
        raise ValueError('invalid CSV') from error
    return records
'''
REFERENCE_REPORT='''from decimal import Decimal, localcontext
from . import parser


def category_totals(csv_text):
    records = parser.parse_records(csv_text)
    digits = max((len(r['amount'].as_tuple().digits) for r in records), default=1)
    with localcontext() as context:
        context.prec = max(28, digits + len(str(len(records))) + 3)
        totals = {}
        for row in records:
            category = row['category']
            totals[category] = totals.get(category, Decimal(0)) + row['amount']
        return [(category, format(total, '.2f')) for category, total in totals.items()]
'''
REFERENCES=dict(zip(ALLOWED,(REFERENCE_PARSER,REFERENCE_REPORT)))
PUBLIC_TEST='''import unittest
from decimal import Decimal
from csvmini.parser import parse_records
from csvmini.report import category_totals
H='id,category,amount\\n'
class CSVTests(unittest.TestCase):
 def test_records(self):self.assertEqual(parse_records(H+'001,Food,1.25\\n'),[dict(id='001',category='Food',amount=Decimal('1.25'))])
 def test_quotes(self):self.assertEqual(parse_records(H+'"0,1","Food, home",2.00\\n')[0]['category'],'Food, home')
 def test_strip(self):self.assertEqual(parse_records(H+'1, Food ,2\\n')[0]['category'],'Food')
 def test_decimal(self):self.assertIsInstance(parse_records(H+'1,A,0.10\\n')[0]['amount'],Decimal)
 def test_totals(self):self.assertEqual(category_totals(H+'1,A,1.20\\n2,A,2.30\\n'),[('A','3.50')])
 def test_order(self):self.assertEqual(category_totals(H+'1,Z,1\\n2,A,2\\n'),[('Z','1.00'),('A','2.00')])
 def test_negative(self):self.assertEqual(category_totals(H+'1,A,1.00\\n2,A,-0.25\\n'),[('A','0.75')])
 def test_precision(self):self.assertEqual(category_totals(H+'1,A,0.10\\n2,A,0.20\\n'),[('A','0.30')])
'''
HOST_TEST='''import unittest
from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import patch
from csvmini import parser,report
H='id,category,amount\\n'
class Acceptance(unittest.TestCase):
 def test_parser_keys_order(self):
  text=H+'0002,B,2\\n0001,A,1\\n';before=text;rows=parser.parse_records(text);self.assertEqual([r['id'] for r in rows],['0002','0001']);self.assertEqual(set(rows[0]),{'id','category','amount'});self.assertEqual(text,before)
 def test_integration_dependency(self):
  original=parser.parse_records
  with ExitStack() as stack:
   p=stack.enter_context(patch.object(parser,'parse_records',return_value=[dict(id='x',category='Normalized',amount=Decimal('1.10'))]))
   for name,value in list(vars(report).items()):
    if value is original:stack.enter_context(patch.object(report,name,p))
   self.assertEqual(report.category_totals('sentinel'),[('Normalized','1.10')]);p.assert_called_once_with('sentinel')
 def test_unicode(self):self.assertEqual(report.category_totals(H+'1, 音乐 ,1.01\\n2,音乐,2.02\\n'),[('音乐','3.03')])
 def test_duplicates(self):self.assertEqual(report.category_totals(H+'1,A,2\\n1,A,2\\n'),[('A','4.00')])
 def test_noncontiguous(self):self.assertEqual(report.category_totals(H+'1,Z,1\\n2,A,2\\n3,Z,3\\n'),[('Z','4.00'),('A','2.00')])
 def test_zero(self):self.assertEqual(report.category_totals(H+'1,A,0.00\\n'),[('A','0.00')])
 def test_cancel(self):self.assertEqual(report.category_totals(H+'1,A,-4.25\\n2,A,4.25\\n'),[('A','0.00')])
 def test_precision(self):self.assertEqual(report.category_totals(H+'1,A,0.10\\n2,A,0.20\\n3,A,-0.05\\n'),[('A','0.25')])
 def test_invalid(self):
  for value in ('abc','','1e2','1_000','--1'):
   with self.subTest(value=value),self.assertRaises(ValueError):parser.parse_records(H+'1,A,'+value+'\\n')
 def test_nonfinite(self):
  for value in ('NaN','Infinity','-Infinity','sNaN'):
   with self.subTest(value=value),self.assertRaises(ValueError):parser.parse_records(H+'1,A,'+value+'\\n')
 def test_scale(self):
  for value in ('1.001','1.000','0.000'):
   with self.subTest(value=value),self.assertRaises(ValueError):parser.parse_records(H+'1,A,'+value+'\\n')
 def test_escaped_quotes(self):self.assertEqual(parser.parse_records(H+'"00,1","Food, ""home""",1.25\\n')[0],dict(id='00,1',category='Food, "home"',amount=Decimal('1.25')))
 def test_header_only(self):self.assertEqual(parser.parse_records(H),[]);self.assertEqual(report.category_totals(H),[])
 def test_case(self):self.assertEqual(report.category_totals(H+'1,Food,1\\n2,food,2\\n'),[('Food','1.00'),('food','2.00')])
 def test_money_forms(self):self.assertEqual([r['amount'] for r in parser.parse_records(H+'1,A, +.50 \\n2,A,-2.\\n')],[Decimal('.50'),Decimal('-2')])
 def test_structure(self):
  for text in ('id,category,\"amount\\n','category,id,amount\\n','id,category,amount\\n1,A\\n','id,category,amount\\n1,A,2,extra\\n','id,category,amount\\n1,"bad,2\\n'):
   with self.subTest(text=text),self.assertRaises(ValueError):parser.parse_records(text)
 def test_blank_lines(self):self.assertEqual(len(parser.parse_records(H+'\\n1,A,1\\n\\n')),1)
 def test_large_exact(self):self.assertEqual(report.category_totals(H+'1,A,123456789012345678901234567890.10\\n2,A,0.20\\n'),[('A','123456789012345678901234567890.30')])
'''
FORMAT_CONTRACT='''CSV uses an exact ordered id,category,amount header, DictReader strict quoting, and skips empty lines. Missing/extra fields and malformed quoting raise ValueError. id is preserved exactly; category is stripped without case folding (empty category is allowed). Amount surrounding whitespace is stripped. ASCII signed decimal notation (including .50 and 2.) is accepted, but exponents, underscores, nonfinite values, and lexical scale >2 (even trailing zeros) are rejected. Summation must remain exact for large amounts. No deduplication. No input mutation.'''
PUBLIC={'README.md':'# csvmini\nStandard library only. Run python -m unittest discover -s tests -v.\n\n'+FORMAT_CONTRACT+'\n','csvmini/__init__.py':'',ALLOWED[0]:BUG_PARSER,ALLOWED[1]:BUG_REPORT,'tests/test_csvmini.py':PUBLIC_TEST,'.gitignore':'__pycache__/\n*.pyc\n'}
def images(fixed=False,hidden=False):
 data=dict(PUBLIC)
 if fixed:data.update(REFERENCES)
 if hidden:data['hidden/test_hidden.py']=HOST_TEST
 return {n:Image(s.encode(),0o644) for n,s in data.items()}
def hashes():return {n:hashlib.sha256(x.data).hexdigest() for n,x in images(hidden=True).items()}
def create(root):
 root=Path(root).resolve();write_images(root,images())
 for path in [root,*root.rglob('*')]:
  if path.is_symlink() or path.stat().st_uid!=os.geteuid():raise ValueError('unsafe_fixture_owner')
  os.chown(path,-1,os.getegid())
 git(root,'init','-q','--initial-branch=canary-fixture');git(root,'config','user.name','Synthetic Canary');git(root,'config','user.email','canary@invalid.local');git(root,'add','README.md','csvmini','tests','.gitignore');git(root,'commit','-q','-m','fixture: buggy cross-file csvmini baseline');assert not git(root,'remote');return git(root,'rev-parse','HEAD')
