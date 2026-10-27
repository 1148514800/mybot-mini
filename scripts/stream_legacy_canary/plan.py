"""Public immutable D02 contract, independent of all earlier UAT batches."""
import hashlib,json
from dataclasses import replace
from pathlib import Path
from scripts.persistent_uat.plan import config_for as base_config
BASELINE='72e5ef74fb574dc9212fca188112ef058e4762e1'
AUTHORIZATION='NOT_GRANTED'
REQUIRED_AUTHORIZATION='GRANTED_1_REQUEST'
BATCH=Path.home()/'.mybot-mini/uat/stream-legacy-canary-20261027'
PORT=8900
LIMITS={'D02':1}
GLOBAL_LIMIT=1
MODELS={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'}
MESSAGE='请分五个自然段介绍一个完全离线运行的Markdown目录索引工具，分别说明用途、输入、索引方式、搜索方式和限制。每段后换行。不调用工具，不读取或修改任何文件。'
FIXTURES={'README.md':'# Disposable diagnostic workspace\nNo user files. No tool use authorized.\n'}
def config_for(batch,provider):
 return replace(base_config(batch,provider),web_streaming=True,web_steer=False,max_react_steps=1,max_completion_tokens=1200)
def contract():
 return dict(version=1,baseline=BASELINE,batch_path=str(BATCH),authorization=AUTHORIZATION,required_authorization=REQUIRED_AUTHORIZATION,case_limits=LIMITS,global_limit=GLOBAL_LIMIT,models=MODELS,message=MESSAGE,port=PORT,fixtures=FIXTURES,
  configuration=dict(stream=True,stream_options={'include_usage':True},web_streaming=True,web_steer=False,tools=[],MCP=False,skills=False,coding=False,semantic_summary=False,sdk_retries=0,max_react_steps=1,input_limit=14000,output_reserve=1200,timeout_seconds=90),
  admission='one Attempt; durable reservation before SDK; durable HTTP gate before transport; original failover policy cannot obtain second reservation',
  browser='fresh 0700 Chrome persistent profile, no user profile; same-origin dual profile isolation; DOM send only; no resend',
  scoring=dict(protocol='normal consumption, legal terminal, natural EOF, confirmed SDK close, no unresolved protocol error AND reliable final persistence',usage='observe numeric provider fields separately from trusted settlement; missing trusted Usage => UNKNOWN, not automatic protocol FAIL',shutdown='own process exit 0 AND stream closed AND port free AND lease released AND SQLite integrity',ui='same browser performance.now submit to visible text before completion; separate from protocol'),
  evidence='at most eight structural chunks including legacy kind/field lengths/extra count/semantic emptiness, fixed error code/index/phase; hashes not full requests/chunks/replies; private native event store retains reply to verify persistence',
  timing='server monotonic admission/chunk/text/SSE; browser performance.now submit/visible. Cross-clock delay UNKNOWN',
  stop=['no fresh exact authorization','changed frozen assets/config/inode/workspace','uncertain execution or budget','any attempted second input/physical request/HTTP','protocol failure: preserve HALT, allow owned cleanup'],
  future_actions=['verify','identity/port/lease/browser/database preflight','start once','new independent Session','DOM send exact message once','wait settlement','record diagnostics','bounded normal owned shutdown','grade independently'],cost=None)
def plan_hash():return hashlib.sha256(json.dumps(contract(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
