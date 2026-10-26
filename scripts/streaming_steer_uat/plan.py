import hashlib,json
from pathlib import Path
from dataclasses import replace
from scripts.persistent_uat.plan import config_for as base_config
BASELINE='3a8a3d67d7305bb55a357b8a851dde0446fc2c4f'
AUTHORIZATION='NOT_GRANTED'
REQUIRED_AUTHORIZATION='GRANTED_8_REQUESTS'
BATCH=Path.home()/'.mybot-mini/uat/streaming-steer-live-20261026'
PORT=8899
LIMITS={'R01':1,'R02':4,'R03':1,'R04':2}
GLOBAL_LIMIT=8
MODELS={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'}
MESSAGES={
'R01':'请用五个简短的自然段，介绍一个只在本地运行的Markdown文件搜索工具：说明用途、输入、搜索方式、结果展示和一个限制。每段后换行。只解释概念，不调用工具，不读取文件，不写文件。',
'R02':'先查看当前目录，再读取README.md，根据实际内容说明该目录的用途。不要修改任何文件；只允许使用list_files和read_file。',
'R03':'请用四行中文解释Python列表推导式，每行一个要点。只解释，不调用工具，不读取或写入文件。',
'R04':'请写一份较长的Markdown说明，分八个小节介绍本地Markdown搜索工具的设计、输入、索引、查询、排序、错误提示、隐私与局限，每节给出解释和示例，并分行展示。只做概念说明，不调用工具，不读取或写入文件。'}
STEER={'R02':'调整顺序：优先读取README.md；不要先读取其他示例文件。然后用两句话说明该目录的用途。不允许修改文件。','R03':'请改为英文回答。'}
FIXTURES={'README.md':'# Lantern Markdown Demo\n用途：此目录演示本地Markdown文件搜索，不联网、不修改输入。\n核心标识：LANTERN-LOCAL-42。\n示例在examples/中；它们不是本次优先读取目标。\n','examples/alpha.md':'# Alpha\n公开示例：咖啡与书签。\n','examples/beta.md':'# Beta\n公开示例：山路与晨光。\n'}
BARRIER={'R01':0,'R02':8,'R03':8,'R04':8}
DIMENSIONS=['Protocol Compatibility','Streaming Integrity','Workflow Success','Tool Safety','Steer Queue Correctness','Steer Application','Model Semantic Adherence','UI Responsiveness','Resource Accounting','Cleanup Integrity']
SCORING={
'R01':['actual stream/include_usage flags and SDK chunks','trusted finish and final normalized SDK text equals saved assistant text','no tool, fallback, retry or second request','preview must become visible before complete; protocol and UX independently scored'],
'R02':['queued via real browser after first chunk and before terminal','original request hash unchanged','unstarted calls paired executed=false','next admitted request contains exact Steer plus actual source event','actual read order respects README priority; no other example read before README','final two sentences use README purpose and LANTERN-LOCAL-42','no writes or permissions; no-next-step is not_applied, never invented PASS'],
'R03':['browser Steer accepted after actual first nonterminal chunk','no next model step => not_applied','one request only; visible not-applied notice; no claim in-flight was steered'],
'R04':['browser Stop after first nonterminal chunk','stream close confirmed and no incomplete tools executed','no partial response persisted as completed','usage absent stays null; remote billing UNKNOWN','no retry/fallback/reconnect model request; service, port and Lease settle']}
def config_for(batch,provider):return replace(base_config(batch,provider),web_streaming=True,web_steer=True,max_react_steps=4,max_completion_tokens=1200,context_recent_turns=2)
def contract():
 return dict(version=1,baseline=BASELINE,authorization=AUTHORIZATION,required_authorization=REQUIRED_AUTHORIZATION,batch_path=str(BATCH),port=PORT,case_order=list(LIMITS),case_limits=LIMITS,global_limit=GLOBAL_LIMIT,models=MODELS,messages=MESSAGES,steer=STEER,fixtures=FIXTURES,barrier=dict(seconds_after_first_nonterminal_chunk=BARRIER,release='first genuine SDK chunk is yielded unchanged, then wait; never wait if first chunk already terminal',no_chunk_mutation=True,premise_failure='BLOCKED, no rerun'),actions={c:['start unique case service','new independent session','send exact registered message','observe SDK first chunk (role is not visible text)',*(['send exact Steer through Web'] if c in STEER else ['click Stop through Web'] if c=='R04' else []),'wait settlement','read-only evidence and independent grading','close own service and verify Lease/port'] for c in LIMITS},scoring=SCORING,dimensions=DIMENSIONS,budgets=dict(input_limit=14000,input_mode='estimate',output_tokens=1200,max_react_steps=4,request_timeout_seconds=90,compaction='deterministic',sdk_max_retries=0,model_window='unknown'),policy=dict(attempts_per_case=1,no_reruns=True,no_budget_transfer=True,summary_and_judge_disabled=True,cost=None,ordinary_semantic_fail='FAIL and continue',unsupported_stream='halt all dependent cases',security_or_unsettled='halt entire batch'),timing=dict(sdk='request admission, HTTP hook, first chunk, close: server process monotonic',browser='submit-to-visible: browser operator process monotonic; record polling uncertainty',sdk_to_dom='UNKNOWN across clock domains; do not subtract without verified correlation',barrier='controlled duration recorded separately, never natural latency'),tool_registry=dict(allowed=['read_file','list_files'],adapter='UAT-only restrictive Registry factory; silently omit native planning registration; no AgentLoop replacement or tool wrapping'),stop_conditions=['no fresh exact authorization','changed source/config/plan/workspace/DB identity','unsettled reservation','budget/retry/authentication anomaly','unexpected tools or unsafe runtime','stream protocol rejection or untrusted stream result','evidence or cleanup cannot be confirmed'])
def plan_hash():return hashlib.sha256(json.dumps(contract(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
