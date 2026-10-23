"""OFFLINE/SYNTHETIC actual metadata and native Preview checks."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.uat.fixtures import create_v2, fingerprint
from scripts.uat.check_environment import check_environment, require_environment
from mybot.tools.patch import ApplyPatchTool

class PreflightChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()/'fixture';create_v2('U04',self.root)
    async def test_compliant_preview_and_bug_confirmed_no_write(self):
        before=fingerprint(self.root);result=await require_environment('U04',self.root)
        self.assertEqual(result['status'],'PASS');self.assertTrue(result['native_previews'][0]['passed'])
        self.assertTrue(result['expected_initial_bug']);self.assertTrue(result['seatbelt_available'])
        self.assertEqual(before,fingerprint(self.root))
    async def test_cross_file_fixture_supported(self):
        root=self.root.parent/'cross';create_v2('U05',root)
        result=await require_environment('U05',root)
        self.assertEqual(len(result['native_previews']),3)
        self.assertTrue(all(p['passed'] for p in result['native_previews']))
        self.assertTrue(result['expected_initial_bug'])
    async def test_group_mismatch_native_preview_rejects(self):
        with patch('mybot.tools.patch.os.getegid',return_value=os.getegid()+10000):
            result=await check_environment('U04',self.root)
        self.assertEqual(result['status'],'BLOCKED');self.assertIn('unsupported_ownership',result['issues'])
        self.assertFalse(result['native_previews'][0]['passed'])
    async def test_xattr_rejected(self):
        path=self.root/'src/clockcache/cache.py';__import__('subprocess').run(['xattr','-w','com.mybot.offline','test',str(path)],check=True)
        result=await check_environment('U04',self.root)
        self.assertEqual(result['status'],'BLOCKED');self.assertIn('unsupported_metadata',result['issues'])
    async def test_acl_rejected(self):
        import subprocess
        path=self.root/'src/clockcache/cache.py'
        subprocess.run(['chmod','+a',f'{os.getlogin()} allow read',str(path)],check=True)
        result=await check_environment('U04',self.root)
        self.assertEqual(result['status'],'BLOCKED');self.assertIn('unsupported_metadata',result['issues'])
    async def test_symlink_rejected(self):
        path=self.root/'src/clockcache/cache.py';path.rename(path.with_suffix('.old'));path.symlink_to(path.with_suffix('.old'))
        self.assertEqual((await check_environment('U04',self.root))['status'],'BLOCKED')
    async def test_stale_hash_rejected(self):
        result=await ApplyPatchTool(self.root,patch_mode='preview').execute(dry_run=True,changes=[dict(
            op='update',path='src/clockcache/cache.py',expected_sha256='0'*64,
            edits=[dict(old_text='import time',new_text='import time\n# preview')])])
        self.assertFalse(result.success);self.assertEqual(result.error,'stale_file_hash')
    async def test_existing_fixture_not_overwritten(self):
        before=fingerprint(self.root)
        with self.assertRaises(FileExistsError):create_v2('U04',self.root)
        self.assertEqual(before,fingerprint(self.root))
    async def test_initial_bug_required(self):
        p=self.root/'src/clockcache/cache.py';p.write_text(p.read_text().replace(' > expires_at',' >= expires_at'))
        with self.assertRaisesRegex(RuntimeError,'fixture_environment_blocked'):await require_environment('U04',self.root)

if __name__=='__main__':unittest.main(verbosity=2)
