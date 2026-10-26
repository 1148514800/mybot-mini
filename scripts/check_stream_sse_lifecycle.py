"""Finite authenticated SSE and diagnostic Web state, no provider network."""
import asyncio,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
import httpx
from mybot.web.server import create_app
from scripts.eventstore_fixtures import configuration
from scripts.streaming_fixtures import Client,Stream,chunk

class Checks(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.client=Client([Stream([chunk('第一行\n'),chunk('第二行\n',finish='stop')],delay=.06)])
  self.app=create_app(configuration(self.root,web_streaming=True,web_steer=True),client_factory=lambda _:self.client)
  self.h=httpx.AsyncClient(base_url='http://127.0.0.1:8765',transport=httpx.ASGITransport(app=self.app));await self.h.get('/')
  self.headers={'Origin':'http://127.0.0.1:8765','X-Mybot-CSRF':(await self.h.get('/api/bootstrap')).json()['csrf']}
  self.sid=(await self.h.post('/api/conversations',json={},headers=self.headers)).json()['id'];self.c=self.app.runtime.conversations[self.sid]
 async def asyncTearDown(self):await self.app.runtime.close();await self.h.aclose();self.tmp.cleanup()
 async def events(self,cursor=0):
  with patch('mybot.web.server.SSE_CONNECTION_SECONDS',.02):return await self.h.get('/api/conversations/'+self.sid+'/events',headers={'Last-Event-ID':str(cursor)})
 async def test_idle_finite(self):
  r=await asyncio.wait_for(self.events(),.5);self.assertEqual(r.status_code,200);self.assertFalse(self.app.runtime.closed)
 async def test_resume_only_new_events(self):
  self.c.emit({'type':'synthetic_one'});first=(await self.events()).text;self.assertIn('synthetic_one',first);cursor=self.c.sequence
  self.c.emit({'type':'synthetic_two'});body=(await self.events(cursor)).text;self.assertIn('synthetic_two',body);self.assertNotIn('synthetic_one',body)
 async def test_future_cursor_reset(self):self.assertIn('id: 0\nevent: reset',(await self.events(999)).text)
 async def test_missed_window_reset(self):
  for i in range(300):self.c.emit({'type':'synthetic'})
  self.assertIn('event: reset',(await self.events()).text)
 async def test_disconnect_does_not_stop_background(self):
  await self.app.runtime.start(self.c,'synthetic');await self.events();self.assertFalse(self.c.task.done());await self.c.task;self.assertEqual(self.c.status,'completed');self.assertEqual(len(self.client.requests),1)
 async def test_refresh_does_not_dispatch(self):
  await self.app.runtime.start(self.c,'synthetic');await self.h.get('/');await self.h.get('/api/bootstrap');await self.events();await self.c.task;await self.events();self.assertEqual(len(self.client.requests),1)
 async def test_safe_code_survives_state_not_raw_diagnostics(self):
  self.client.streams=[Stream([chunk('preview\n',finish='stop'),chunk(finish='stop')])];await self.app.runtime.start(self.c,'synthetic');await self.c.task
  s=(await self.h.get('/api/conversations/'+self.sid)).json();self.assertEqual(s['stream_preview']['error_code'],'stream_duplicate_finish');self.assertNotIn('recent_chunks',json.dumps(s['stream_preview']));self.assertEqual(s['status'],'provider_error')
 async def test_last_event_id_invalid(self):
  r=await self.h.get('/api/conversations/'+self.sid+'/events',headers={'Last-Event-ID':'private-invalid'});self.assertEqual(r.status_code,400)

def check_stream_sse_lifecycle():
 r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
 if not r.wasSuccessful():raise AssertionError('SSE lifecycle failed')
if __name__=='__main__':check_stream_sse_lifecycle()
