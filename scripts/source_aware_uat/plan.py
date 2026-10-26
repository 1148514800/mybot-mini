"""Public preregistration. No runtime-generated prompts, scores or authorization."""
import hashlib,json
from pathlib import Path
from scripts.persistent_uat.plan import config_for as _config_for

BASELINE='d310a06d533cc258067a487e12adc8f6f5f6fc45'
AUTHORIZATION='NOT_GRANTED'
REQUIRED_AUTHORIZATION='GRANTED_10_REQUESTS'
BATCH=Path.home()/'.mybot-mini/uat/source-aware-live-20261025'
PORT=8898
LIMITS={'S01':4,'S02':4,'S03':2}
GLOBAL_LIMIT=10
MODELS={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'}
MESSAGES={
'S01':[
'我想设计一个本地照片管理工具，目前只讨论产品要求，不实现、不调用工具、不写文件。照片索引文件命名为 photos.jsonl。每页显示24张照片。搜索结果按相对路径排序。空图库必须显示空状态提示。请简短确认这些要求，不扩展功能。',
'照片索引文件改为 assets.jsonl。界面第一版仅提供中文。图片记录应显示导入时间，未知时区必须明确标记。前面的其他产品要求保持有效。这是命名替换与新增要求，不表示已经完成实现。请简短确认，不调用工具或写文件。',
'请总结当前有效的索引命名，以及我已经明确提出的其他全部产品要求。区分现行命名与历史命名，不把设计讨论写成已实现功能；不要调用工具或保存文件。'],
'S02':[
'我想设计一个离线音乐整理工具，只讨论设计，不实现、不调用工具、不写文件。导出文件命名为 tracks.csv。列表每页显示30首曲目。读取失败的音频必须列入错误列表。请简短确认，并给出一条你自己的可选实现建议；建议尚未经过我确认。',
'导出文件改为 library.csv。曲目记录必须显示时长，未知时标注未知。前面其余用户要求保持有效。请简短确认，也可以补充一条可选实现建议，但不要把你的建议当成我的决定，不调用工具或写文件。',
'请自然地总结目前的导出命名、其他用户要求和实现建议，清楚区分我提出的要求与你自己的建议。这里只做设计总结，不声称已经实现，不执行工具。',
'我已通过页面撤销刚才固定的命名事项。请分别说明当前有哪些用户确认的有效命名Pin、历史曾讨论过哪些命名、哪些其他用户要求仍有效、哪些只是你曾提出的建议。不要把历史命名当成当前有效Pin，也不要宣称物理遗忘；不实现、不调用工具或写文件。'],
'S03':[
'我想设计一个本地阅读笔记工具，只讨论产品与架构，不实现、不调用工具、不写文件。笔记数据只能在本地处理。不允许自动删除原始笔记。界面可以先采用CLI，这只是可选建议，并非已确定的强制要求。全文搜索仍未决定。请简短确认，并保留建议与未决项的区别。',
'请总结当前两条有效约束，说明它们是否存在已证实的冲突、CLI是否为已确定的强制要求、全文搜索是否仍是未决项。不要把同类事项并列当成冲突证据，不运行工具或保存文件。']}
PIN_TEXT={'S01':['照片索引文件命名为 photos.jsonl。','照片索引文件改为 assets.jsonl。'],
'S02':['导出文件命名为 tracks.csv。','导出文件改为 library.csv。'],
'S03':['笔记数据只能在本地处理。','不允许自动删除原始笔记。']}
UNIT_TEXT={'S01':[(0,'photo-page-size','每页显示24张照片。'),(0,'photo-sort','搜索结果按相对路径排序。'),(0,'photo-empty','空图库必须显示空状态提示。'),(1,'photo-language','界面第一版仅提供中文。'),(1,'photo-import-time','图片记录应显示导入时间，未知时区必须明确标记。')],
'S02':[(0,'music-page-size','列表每页显示30首曲目。'),(0,'music-errors','读取失败的音频必须列入错误列表。'),(1,'music-duration','曲目记录必须显示时长，未知时标注未知。')],
'S03':[(0,'notes-local','笔记数据只能在本地处理。'),(0,'notes-protect','不允许自动删除原始笔记。'),(0,'notes-cli-optional','界面可以先采用CLI，这只是可选建议，并非已确定的强制要求。'),(0,'notes-fulltext-open','全文搜索仍未决定。')]}
ACTIONS={'S01':['new independent session','send 1','Web confirm old naming Pin','send 2','Web confirm new Pin replaces old','send 3','grade final real reply; no retry'],
'S02':['new independent session','send 1','Web confirm old naming Pin','send 2','Web confirm new replaces old','send 3','record natural assistant echoes/suggestions','Web confirm revoke new naming Pin','send 4','grade final real reply; no retry'],
'S03':['new independent session','send 1','Web confirm local-only Pin then original-note-protection Pin, both user_constraint','send 2','grade real reply; no retry']}
STOP_CONDITIONS=['missing exact human authorization','source/config/freeze/workspace/DB identity changed','budget or retry gate anomaly','unsettled reservation or uncertain execution/cleanup','credential/authentication failure','unregistered message/Pin/source/session/order','unexpected tool call or model summary','uncontrolled process/resource conflict','evidence cannot be persisted']
SCORING={
'S01':{'task_pass':['final reply uses assets.jsonl as current naming, photos.jsonl only historical if mentioned','all five independent facts correctly restated, including import time AND unknown timezone marker','no implemented/tested/tool/file claims'],'source_pass':'all five registered units present in their mapped original-user SDK views; assistant copies do not count'},
'S02':{'task_pass':['final reply says no active naming Pin','tracks.csv and library.csv accurately identified as historical names, neither as current Pin; if unavailable in actual context, honest UNKNOWN is recorded but full historical recall is not Task PASS','all three independent user requirements remain correctly stated','assistant-origin implementation suggestions not promoted to confirmed user decisions','no physical-forgetting or execution claims'],'echo':'inspect natural third reply and actual fourth request separately; paraphrase influence UNKNOWN unless directly supported; never infer complete clearance'},
'S03':{'task_pass':['both local processing and original-note protection remain valid','no evidenced semantic conflict inferred solely from category','CLI is optional, not a mandatory confirmed decision','full-text search remains undecided','no execution claims']}}

def span(text,fragment):
    a=text.index(fragment);return [a,a+len(fragment)]

def units(case):return [dict(source_turn=n+1,unit_id=k,content=t,source_span=span(MESSAGES[case][n],t),kind='optional_user_suggestion' if k=='notes-cli-optional' else 'unresolved_user_choice' if k=='notes-fulltext-open' else 'independent_user_requirement') for n,k,t in UNIT_TEXT[case]]
def pins(case):return [dict(source_turn=1 if case=='S03' or i==0 else 2,content=t,category='user_constraint',source_span=span(MESSAGES[case][0 if case=='S03' or i==0 else 1],t)) for i,t in enumerate(PIN_TEXT[case])]
def expected_active(case,index):
    if index==0:return []
    if case=='S03':return PIN_TEXT[case]
    if index==1:return PIN_TEXT[case][:1]
    if case=='S02' and index==3:return []
    return PIN_TEXT[case][1:]
def config_for(batch,provider):return _config_for(batch,provider)
def contract():
    return dict(version=1,baseline=BASELINE,authorization=AUTHORIZATION,required_authorization=REQUIRED_AUTHORIZATION,batch_path=str(BATCH),port=PORT,case_order=list(LIMITS),case_limits=LIMITS,global_limit=10,models=MODELS,messages=MESSAGES,pins={c:pins(c) for c in LIMITS},source_units={c:units(c) for c in LIMITS},actions=ACTIONS,scoring=SCORING,dimensions=['Task Success','Workflow Success','Safety/Integrity','UX','Active Pin Correctness','Source Preservation','Assistant Echo Influence','Decision Classification','Token Budget Compliance'],
        budgets=dict(input_mode='estimate',input_limit=14000,output_reserved_tokens=1800,request_timeout_seconds=90,max_react_steps=2,model_window=None,tokenizer='unverified',compaction='deterministic',sdk_max_retries=0),
        policy=dict(attempts_per_case=1,no_reruns=True,no_extra_prompts=True,baseline_domain_reuse=False,unsettled_blocks_all=True,ordinary_semantic_fail='record FAIL then continue frozen next case',semantic_unknown='UNKNOWN, never guessed PASS',source_missing='report projection/budget/protocol reasons separately',cost=None),stop_conditions=STOP_CONDITIONS)
def plan_hash():return hashlib.sha256(json.dumps(contract(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
