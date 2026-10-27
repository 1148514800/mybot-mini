"""Trusted public fixture and host-only suites. Candidate is never imported here."""
import hashlib,os,subprocess
from pathlib import Path
from mybot.evaluation.coding_fixtures import Image,write_images
from .plan import ALLOWED
BUG='''def search_notes(query, notes):
    return sorted({note["id"] for note in notes if query in note["title"]})
'''
REFERENCE='''def search_notes(query, notes):
    needle = query.strip().casefold()
    if not needle:
        return []
    return [note["id"] for note in notes
            if needle in note["title"].casefold() or needle in note["body"].casefold()]
'''
PUBLIC_TEST='''import unittest
from notesearch.search import search_notes
class SearchTests(unittest.TestCase):
 def test_title(self):self.assertEqual(search_notes('cat',[dict(id='b',title='cat',body='')]),['b'])
 def test_body(self):self.assertEqual(search_notes('cat',[dict(id='b',title='',body='cat')]),['b'])
 def test_case(self):self.assertEqual(search_notes('CAT',[dict(id='b',title='Cat',body='')]),['b'])
 def test_blank(self):self.assertEqual(search_notes('  ',[dict(id='b',title='  ',body='')]),[])
 def test_order(self):self.assertEqual(search_notes('x',[dict(id='z',title='x',body=''),dict(id='a',title='x',body='')]),['z','a'])
'''
HOST_TEST='''import copy,unittest
from notesearch.search import search_notes
class Acceptance(unittest.TestCase):
 def test_title_only(self):self.assertEqual(search_notes('  red ',[dict(id=1,title='red',body='blue')]),[1])
 def test_body_only(self):self.assertEqual(search_notes('river',[dict(id=2,title='sky',body='a river')]),[2])
 def test_both(self):self.assertEqual(search_notes('x',[dict(id=2,title='x',body='x')]),[2])
 def test_mixed(self):self.assertEqual(search_notes('cAt',[dict(id=2,title='CAT',body=''),dict(id=3,title='',body='Cat')]),[2,3])
 def test_order(self):self.assertEqual(search_notes('x',[dict(id=9,title='x',body=''),dict(id=1,title='x',body='')]),[9,1])
 def test_duplicates(self):self.assertEqual(search_notes('x',[dict(id=2,title='x',body=''),dict(id=2,title='',body='x')]),[2,2])
 def test_empty(self):
  for q in ('','   ','\\t\\n'):self.assertEqual(search_notes(q,[dict(id=1,title='',body='  ')]),[])
 def test_unicode(self):self.assertEqual(search_notes('STRASSE',[dict(id=1,title='Straße',body='')]),[1])
 def test_no_match(self):self.assertEqual(search_notes('absent',[dict(id=1,title='present',body='other')]),[])
 def test_unchanged(self):
  notes=[dict(id=3,title='River',body='x'),dict(id=2,title='sky',body='river')];before=copy.deepcopy(notes);self.assertEqual(search_notes('river',notes),[3,2]);self.assertEqual(notes,before)
'''
PUBLIC={'README.md':'# notesearch-mini\nA standard-library-only note search exercise. Run python -m unittest discover -s tests -v.\n','notesearch/__init__.py':'',ALLOWED:BUG,'tests/test_search.py':PUBLIC_TEST,'.gitignore':'__pycache__/\n*.pyc\n'}
def images(fixed=False,hidden=False):
 data=dict(PUBLIC)
 if fixed:data[ALLOWED]=REFERENCE
 if hidden:data['hidden/test_hidden.py']=HOST_TEST
 return {n:Image(s.encode(),0o644) for n,s in data.items()}
def hashes():return {n:hashlib.sha256(x.data).hexdigest() for n,x in images(hidden=True).items()}
def git(root,*args):
 env={**os.environ,'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_TERMINAL_PROMPT':'0','GIT_OPTIONAL_LOCKS':'0'}
 return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-c','core.autocrlf=false','-C',str(root),*args],env=env,stderr=subprocess.PIPE).decode().strip()
def create(root):
 root=Path(root).resolve();write_images(root,images())
 # /private/tmp can inherit wheel GID. Normalize only this newly-created owned fixture, never weaken native Patch checks.
 for p in [root,*root.rglob('*')]:
  if p.is_symlink() or p.stat().st_uid!=os.geteuid():raise ValueError('unsafe_fixture_owner')
  os.chown(p,-1,os.getegid())
 git(root,'init','-q','--initial-branch=canary-fixture');git(root,'config','user.name','Synthetic Canary');git(root,'config','user.email','canary@invalid.local');git(root,'add','README.md','notesearch','tests','.gitignore');git(root,'commit','-q','-m','fixture: frozen buggy notesearch baseline');assert not git(root,'remote');return git(root,'rev-parse','HEAD')
