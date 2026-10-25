"""Pre-registered public messages, actions and limits. No live authorization."""
import hashlib,json
from pathlib import Path
from mybot.config import GatewayConfig

BASELINE='75cfcd6e1e04ab4d755aa2edf541a08dfedc9da7'
LIVE_AUTHORIZATION='NOT_GRANTED'
LIMITS={'L01':10,'L02':4,'L03':2}
GLOBAL_LIMIT=16
MODELS={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'}
BATCH=Path.home()/'.mybot-mini/uat/persistent-session-20261025'
PINS=['所有文档扫描必须在本地进行。','不得自动删除或修改原始Markdown文件。']
OLD='索引文件命名为 index.md。'
NEW='索引文件改为 catalog.md。'
MESSAGES={
'L01':[
'我想设计一个本地Markdown文档管理工具，先讨论产品与架构，不实现、不调用工具、不写文件。所有文档扫描必须在本地进行。不得自动删除或修改原始Markdown文件。请简短确认目标和边界。',
'输入范围由用户明确选择一个根目录，子目录可以递归查看；符号链接默认不跟随，权限不足应记录跳过原因。第一版先支持.md扩展名，大小写不敏感。目录变动时报告只代表本次观察。请建议一个简洁的输入约定，只讨论设计。',
'元数据需要记录相对路径、标题、修改时间、文件大小和读取状态。标题优先取第一个一级标题，缺失时用文件名显示并标注来源；无法解码的文件进入错误列表。请说明字段及缺失值的表达方式，不生成代码。',
'搜索先提供文件名和标题的关键词匹配，结果需要解释命中位置。是否支持正文全文搜索仍未决定，暂时也没有确定分词方案。请比较两种简单的搜索设计，并保留这些待定项，不开展实现。',
'索引是派生数据，先讨论JSON Lines与SQLite两种候选格式；尚未选定最终格式。每条记录应有schema版本，导出要稳定排序。索引文件名也尚未决定。请给出取舍建议，不把建议当成已确认决定。',
'去重分为路径重复和内容相同两种候选，文件名相同不足以判定内容一致。建议列表要说明比较依据和读取失败情况，内容哈希算法仍未选定。请说明如何避免把候选误报成确定结论。',
'增量扫描可以比较相对路径、大小和时间，但这些线索不保证内容没有变化；需要考虑原子替换、重命名和中途取消。尚未确定缓存失效策略与一致性保证。请提出最小设计，清楚区分观察、推断与待确认。',
'界面第一版可以用命令行，展示扫描进度、错误和待确认项；取消后只能显示部分结果。元数据结构、索引格式、全文搜索和缓存策略还没有完成实现或测试。请整理未决技术问题，不要将设计讨论写成已完成工作。',
'请总结目前有效的产品约束与设计建议，并分开列出已确定、尚未决定和未实现的内容。尤其回顾最早确认的两项核心边界，不要运行工具或保存文件。'],
'L02':[
OLD+'列表默认每页显示20条。搜索结果按相对路径排序。空目录显示空状态说明。这里只确认设计，不实现、不调用工具。',
NEW+'界面第一版只需中文。索引条目展示相对路径。这是新的命名决定，其他描述仍是设计讨论，不代表已经实现。',
'现在有效的索引命名要求是什么？请区分当前确认要求与旧版本，不声称已经创建索引文件，也不要调用工具。',
'我已经撤销刚才固定的命名事项。请说明当前是否还有用户确认的有效命名约束；可以区分历史讨论与当前有效项，不要宣称物理遗忘旧内容，不实现或调用工具。'],
'L03':['继续此前的Markdown项目设计讨论，请总结当前有效的两项核心约束和仍待决定的问题。只讨论，不执行工具，不写文件。']}
UNITS={'old-page-size':'列表默认每页显示20条。','old-sort':'搜索结果按相对路径排序。','old-empty-state':'空目录显示空状态说明。','new-language':'界面第一版只需中文。','new-relative-path':'索引条目展示相对路径。'}
ACTIONS={'L01':['new conversation','send 1','confirm both source pins','send 2..9','record session id/title/source/event count/final turn'],
'L02':['new distinct conversation','send 1','confirm OLD pin','send 2','confirm NEW replaces OLD','try stale OLD revision; expect rejection','send 3','confirm revoke NEW','send 4','record both source turns and independent units'],
'L03':['record L01 state and ledger totals','normal server shutdown','verify process exit and lease free','restart same frozen entry with L03','select L01 id','compare restored state; no approval/receipt/verified','send 1']}

def span(message,text):
    start=message.index(text);return [start,start+len(text)]

def preregistration():
    return dict(version=1,baseline=BASELINE,authorization=LIVE_AUTHORIZATION,order=list(LIMITS),global_limit=16,case_limits=LIMITS,models=MODELS,messages=MESSAGES,actions=ACTIONS,
        pins={'L01':[dict(content=p,span=span(MESSAGES['L01'][0],p),source_turn=1) for p in PINS],
              'L02':[dict(content=OLD,span=span(MESSAGES['L02'][0],OLD),source_turn=1),dict(content=NEW,span=span(MESSAGES['L02'][1],NEW),source_turn=2)]},
        independent_units={k:dict(content=v,source_turn=1 if k.startswith('old-') else 2) for k,v in UNITS.items()},
        budgets=dict(mode='estimate',input_limit=14000,output_tokens=1800,request_timeout_seconds=90,max_react_steps=2,compaction='deterministic',model_window='unknown; input cap enforced, no invented provider window'),
        scoring=dict(dimensions=['Task Success','Workflow Success','Safety/Integrity','UX','Source Integrity','Active Pin Correctness','Model Request Inclusion','Semantic Adherence','Supersession Correctness','Revocation Correctness','Historical Information Loss'],
          rule='Independent human grading of redacted real replies and request metadata. Inclusion is not semantic adherence. Unknown or unrun is BLOCKED, never synthetic PASS. No paid judge. One attempt per case; no retries.'),
        batch_path=str(BATCH),cost=None)

def plan_hash():return hashlib.sha256(json.dumps(preregistration(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def config_for(batch,provider):
    batch=Path(batch).resolve()
    return GatewayConfig(workspace=batch/'workspace',session_backend='event_sqlite',session_persist=False,session_event_path=batch/'private/session-events.sqlite3',session_max_turns=6,
        provider='coco',model=provider['model'],api_key=provider.get('api_key'),base_url=provider['base_url'],
        coding_enabled=False,coding_file_access='read_only',coding_patch_mode='off',coding_preview_receipt=False,coding_command={'mode':'off'},coding_autonomy={'enabled':False},coding_git_workflow={'enabled':False},
        mcp_enabled=False,mcp_servers={},mcp_discovery={},skills_enabled=False,debug=False,max_react_steps=2,max_completion_tokens=1800,request_timeout_seconds=90,
        context_enabled=True,context_max_chars=40000,context_recent_turns=2,context_summary_max_chars=1000,context_tool_result_max_chars=1000,
        context_token_budget={'mode':'estimate','input_limit':14000},context_compaction={'mode':'deterministic'})
