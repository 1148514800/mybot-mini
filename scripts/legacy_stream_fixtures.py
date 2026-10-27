"""Public Synthetic legacy packets, not a replay of private D01 data."""
import json
import httpx
from openai import AsyncOpenAI
from scripts.streaming_fixtures import chunk
MISSING=object()
USAGE=dict(prompt_tokens=7,completion_tokens=9,total_tokens=16)
def packets(value=MISSING,*,count=221,usage=True):
 result=[chunk('Synthetic local preview.\n' if i==0 else 'x') for i in range(count-1)]
 final=chunk('',finish='stop');final['choices'][0]['delta'].update(role='assistant',tool_calls=[])
 if value is not MISSING:final['choices'][0]['delta']['function_call']=value
 result.append(final)
 if usage:result.append(dict(choices=[],usage=USAGE))
 return result

def client(frames,counter):
 async def handler(request):
  counter.append(json.loads(request.content))
  body=''.join('data: '+json.dumps(dict(id='synthetic',object='chat.completion.chunk',created=1,model='synthetic',**p))+'\n\n' for p in frames)+'data: [DONE]\n\n'
  return httpx.Response(200,headers={'content-type':'text/event-stream'},text=body)
 return AsyncOpenAI(api_key='synthetic',base_url='http://mock.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
