"""New contract; no old allowance or private batch is inherited."""
import hashlib,json
from pathlib import Path
from dataclasses import replace
from scripts.persistent_uat.plan import config_for as base_config
BASELINE='e9d04f2c28fb46c0216df362170beaeaeccd452d'
AUTHORIZATION='NOT_GRANTED'
REQUIRED_AUTHORIZATION='GRANTED_2_REQUESTS'
BATCH=Path.home()/'.mybot-mini/uat/streaming-steer-recovery-v3-20261027'
PORT=8902
LIMITS={'N01':1,'N02':1}
GLOBAL_LIMIT=2
MODELS={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'}
MESSAGES={'N01':'请用四句话简要解释Python列表推导式，不调用工具。','N02':'请用较长的中文Markdown说明介绍一个完全离线的文档检索工具，分多个章节详细说明输入、索引、查询、结果展示、错误处理及使用限制，不调用工具，不修改文件。'}
STEER={'N01':'请改为英文回答。'}
BARRIER={'N01':8,'N02':8}
FIXTURES={}
def config_for(batch,provider):return replace(base_config(batch,provider),web_streaming=True,web_steer=True,max_react_steps=4,max_completion_tokens=1200)
def contract():
 return dict(version=3,name='streaming-steer-recovery-canary-v3',baseline=BASELINE,batch_path=str(BATCH),authorization=AUTHORIZATION,required_authorization=REQUIRED_AUTHORIZATION,port=PORT,case_order=list(LIMITS),case_limits=LIMITS,global_limit=GLOBAL_LIMIT,models=MODELS,messages=MESSAGES,steer=STEER,fixtures=FIXTURES,
 configuration=dict(stream=True,stream_options={'include_usage':True},sdk_retries=0,tools=[],MCP=False,skills=False,coding=False,summary=False,judge=False,input_limit=14000,output_reserve=1200,timeout_seconds=90,max_react_steps=4),
 barrier=dict(seconds=BARRIER,scope='first real nonterminal chunk yielded then consumer resumes; first stream only',first_terminal='INCONCLUSIVE without fake window or rerun',chunk_mutation=False,timing='actual barrier separately measured, never natural provider delay'),
 scoring={'N01':['real DOM Steer after genuine delivery','queued then not_applied if no next step','one real physical request only','unchanged in-flight request','UI not-applied notice and explicit next-turn action','refresh/SSE reconnect no resend'], 'N02':['real DOM Stop after genuine delivery','SDK closed, untrusted partial not complete','no tools/retry/fallback','Usage null unless trustworthy','native stopped state; database consistency; exit0, lease/profile release']},
 lifecycle='N01 then N02, unique Attempt each; no transfer/reruns; protocol/authority/ledger/cleanup uncertainty HALTs; existing HALT never cleared and never prevents owned cleanup',stages=['queued','native_on_dispatch_admitted','durable_reservation','HTTP_dispatched','provider_response_observed','independent_semantic_review'],
 evidence='bounded structure, hashes, source IDs, safe screenshots; no original requests/chunks/replies, arguments, cookie or credentials',cost=None)
def plan_hash():return hashlib.sha256(json.dumps(contract(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
