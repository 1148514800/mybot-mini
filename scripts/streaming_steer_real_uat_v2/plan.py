"""Frozen public messages, six physical requests, no Live authorization."""
import hashlib,json
from pathlib import Path
from dataclasses import replace
from scripts.persistent_uat.plan import config_for as base_config
BASELINE='54eeeb80be0cdef65f25affc6eae6c907474cb19'
AUTHORIZATION='NOT_GRANTED'
REQUIRED_AUTHORIZATION='GRANTED_6_REQUESTS'
BATCH=Path.home()/'.mybot-mini/uat/streaming-steer-real-v2-20261026'
PORT=8901
LIMITS={'T01':4,'T02':1,'T03':1}
GLOBAL_LIMIT=6
MODELS={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'}
MESSAGES={
'T01':'请先列出当前目录，再读取README.md，根据文件内容说明这个项目的用途。只允许使用list_files和read_file，不修改任何文件。请根据真实读取结果回答，不要猜测。',
'T02':'请用四句话解释Python列表推导式。不要调用工具。',
'T03':'请写一份较长的中文Markdown说明，分八个章节介绍完全离线的Markdown目录检索工具，依次说明目标、输入、索引、查询、排序、结果展示、错误处理与限制，每章给出解释和示例并分行展示。只做概念说明，不调用工具，不读取、修改或删除任何文件。'}
STEER={'T01':'调整执行顺序：优先读取README.md，不要读取其他示例文件。确认README内容后，用两句话说明项目用途，并包含README中的项目标识。不要修改文件。','T02':'改为英文回答。'}
BARRIER={'T01':8,'T02':0,'T03':8}
IDENTIFIER='RIVER-READONLY-73'
FIXTURES={'README.md':'# River Markdown Search\n项目为纯本地Markdown搜索工具。\n不使用外部网络。\n只读取本地Markdown文档。\n公开标识：RIVER-READONLY-73。\n','examples/alpha.md':'# Alpha\n公开示例：河流与书签。\n','examples/beta.md':'# Beta\n公开示例：山路与晨光。\n'}
def config_for(batch,provider):return replace(base_config(batch,provider),web_streaming=True,web_steer=True,max_react_steps=4,max_completion_tokens=1200)
def contract():
 return dict(version=2,baseline=BASELINE,batch_path=str(BATCH),authorization=AUTHORIZATION,required_authorization=REQUIRED_AUTHORIZATION,case_order=list(LIMITS),case_limits=LIMITS,global_limit=GLOBAL_LIMIT,port=PORT,models=MODELS,messages=MESSAGES,steer=STEER,fixtures=FIXTURES,barrier=dict(seconds=BARRIER,scope='first genuine SDK stream per case only; after first nonterminal chunk yielded and consumer resumes iterator; T02 has no artificial barrier',chunk_mutation=False,first_terminal='premise INCONCLUSIVE, no fake window or rerun',timing='actual wait separately measured, never natural provider latency'),
  configuration=dict(stream=True,stream_options={'include_usage':True},web_streaming=True,web_steer=True,tool_registry={'T01':['list_files','read_file'],'T02':[],'T03':[]},MCP=False,skills=False,coding=False,summary=False,judge=False,sdk_retries=0,input_limit=14000,output_reserve=1200,timeout_seconds=90,max_react_steps=4),
  scoring={'T01':['correct turn/exact Steer DOM queued/persistent user event','in-flight request hashes unchanged','valid assembled real tool calls; unstarted calls executed=false and paired','next native admission distinct from reservation/HTTP/response','exact Steer and source event in SDK and wire messages','read README first after steer; no examples; real result carries identifier','two-sentence purpose reply contains identifier; no invented execution'], 'T02':['genuine first nonterminal chunk then DOM Steer queued','no next request: not_applied, UI notice, no automatic model resend','premise missed => INCONCLUSIVE, do not rerun'], 'T03':['DOM Stop after genuine nonterminal delivery','SDK close; no trusted partial, no tools/retry/fallback','Usage null when unconfirmed; SSE refresh cannot send model','exit0 + port/lease/db consistency']},
  evidence='bounded safe metadata, source IDs and hashes; no full requests, reply/chunks, arguments, credentials or cookie; native private event DB persists original source and reply only',
  lifecycle='one Attempt each, ordered T01 T02 T03, no transfer/rerun. Ordinary semantic/premise failure may continue; protocol/security/uncertainty/ledger anomaly HALTs batch; HALT never prevents owned cleanup',
  stages=['queued','native_on_dispatch_admitted','durable_reservation','HTTP_dispatched','provider_response_observed','semantic_adherence'],
  note='applied is native on_dispatch admission, possibly even before UAT reservation; never evidence of HTTP or remote comprehension',cost=None)
def plan_hash():return hashlib.sha256(json.dumps(contract(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
