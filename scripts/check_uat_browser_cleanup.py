"""Exception ordering tests; fake driver only, no user Chrome or Provider."""
import os,shutil,unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
from scripts.uat_operator.browser_resources import browser_session
from scripts.uat_operator.ports import OperatorError

class CleanupChecks(unittest.TestCase):
 def exercise(self,primary=None,close_error=False,remove_error=False,launch_error=False,unproven=False):
  record={};order=[];seen=[]
  class Context:
   browser=N(version='synthetic')
   def cookies(self):return []
   def close(self):
    order.append('close')
    if close_error:raise RuntimeError('PRIVATE_COOKIE')
  class Chromium:
   def launch_persistent_context(self,path,**kw):
    seen.append(Path(path))
    if launch_error:raise RuntimeError('PRIVATE_LAUNCH')
    return Context()
  @contextmanager
  def factory():
   order.append('driver_enter')
   try:yield N(chromium=Chromium())
   finally:order.append('driver_exit')
  def inspect(path):
   if order[-1]=='driver_exit':return []
   return [] if unproven else [dict(pid=123,uid=os.getuid(),args=['chrome','--user-data-dir='+str(path)])]
  def remove(path):
   order.append('remove')
   if remove_error:raise OSError('PRIVATE_PATH')
   shutil.rmtree(path)
  error=None
  try:
   with browser_session('synthetic',record,factory=factory,inspect_processes=inspect,remove=remove):
    if primary:raise OperatorError(primary)
  except BaseException as exc:error=exc
  finally:
   for p in seen:
    if p.exists() and not p.is_symlink():shutil.rmtree(p)
  return record,order,error
 def test_normal_order_once(self):
  r,o,e=self.exercise();self.assertIsNone(e);self.assertEqual(r['context_close_calls'],1);self.assertLess(o.index('close'),o.index('driver_exit'));self.assertTrue(r['automatic_cleanup_pass'])
 def test_chrome_launch_failure(self):
  r,o,e=self.exercise(launch_error=True);self.assertEqual(r['context_close_calls'],0);self.assertEqual(r['primary_error'],'browser_operation_failed');self.assertTrue(r['profile_removed'])
 def test_after_context_service_failure(self):self.assertEqual(self.exercise('service_start_failed')[0]['primary_error'],'service_start_failed')
 def test_eaddrinuse_primary_preserved(self):self.assertEqual(self.exercise('port_in_use',close_error=True)[0]['primary_error'],'port_in_use')
 def test_navigation(self):self.assertEqual(self.exercise('page_navigation_failed')[0]['primary_error'],'page_navigation_failed')
 def test_steer(self):self.assertEqual(self.exercise('steer_submission_failed')[0]['primary_error'],'steer_submission_failed')
 def test_sse_disconnect(self):self.assertTrue(self.exercise('sse_disconnected')[0]['automatic_cleanup_pass'])
 def test_model_failure(self):self.assertEqual(self.exercise('model_task_failed')[0]['primary_error'],'model_task_failed')
 def test_screenshot(self):self.assertEqual(self.exercise('page_screenshot_failed')[0]['context_close_calls'],1)
 def test_close_failure_no_false_pass(self):
  r,o,e=self.exercise(close_error=True);self.assertEqual(r['context_close_error'],'context_close_failed');self.assertFalse(r['automatic_cleanup_pass']);self.assertTrue(r['profile_removed']);self.assertEqual(o.count('close'),1)
 def test_profile_remove_failure(self):
  r,_,_=self.exercise(remove_error=True);self.assertEqual(r['profile_cleanup_error'],'profile_remove_failed');self.assertTrue(r['cleanup_uncertain']);self.assertFalse(r['automatic_cleanup_pass'])
 def test_combined_errors(self):
  r,_,e=self.exercise('port_in_use',close_error=True,remove_error=True);self.assertEqual(e.code,'port_in_use');self.assertEqual(r['context_close_error'],'context_close_failed');self.assertEqual(r['profile_cleanup_error'],'profile_remove_failed');self.assertNotIn('PRIVATE',str(r))
 def test_identity_failure(self):self.assertEqual(self.exercise(unproven=True)[0]['primary_error'],'browser_identity_unproven')
 def test_service_stop_timeout_classification(self):
  r,_,_=self.exercise('service_stop_timeout');self.assertEqual(r['primary_error'],'service_stop_timeout')
 def test_unproven_profile_never_removed(self):
  from scripts.uat_operator.browser_resources import profile_safe
  with __import__('tempfile').TemporaryDirectory() as t:
   p=Path(t).resolve();self.assertFalse(profile_safe(p,p.parent,(-1,-1)))
if __name__=='__main__':unittest.main()
