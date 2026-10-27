import hashlib,json
from dataclasses import replace
from pathlib import Path
from scripts.persistent_uat.plan import config_for as base
BASELINE='c56a03813f9a0472d72d96e5bc3915ff667f0d60'
AUTHORIZATION='NOT_GRANTED'
REQUIRED_AUTHORIZATION='GRANTED_18_REQUESTS'
BATCH=Path.home()/'.mybot-mini/uat/coding-cross-file-canary-v2-20261027'
PORT=8904
LIMITS={'C02':18}
GLOBAL_LIMIT=18
ALLOWED=('csvmini/parser.py','csvmini/report.py')
COMMAND=['python','-m','unittest','discover','-s','tests','-v']
MESSAGE='请修复 csvmini/parser.py 和 csvmini/report.py，使 parse_records 能使用 csv.DictReader 正确解析带 id、category、amount 表头的 CSV，支持引号和逗号字段，保持 id 原文，去除 category 首尾空白，并将合法金额精确转换为 Decimal；非法或非有限金额、超过两位的小数必须抛出 ValueError。category_totals 必须调用 parse_records，按照类别首次出现顺序精确汇总，返回类别与固定两位小数字符串组成的元组列表，不允许排序或去重。请同时修复这两个模块，不修改其他文件。先阅读代码和测试，使用原生 apply_patch 预览、Receipt 提交，然后运行 python -m unittest discover -s tests -v。测试失败时不得声明修复完成。'
TOOLS={'read_file','list_files','search_code','read_file_range','git_status','git_diff','apply_patch','run_command','create_plan','update_plan','record_task_contract'}
def config_for(batch,provider):
 return replace(base(batch,provider),coding_enabled=True,coding_patch_mode='write',coding_file_access='read_only',coding_preview_receipt=True,coding_command=dict(mode='macos_readonly',timeout_seconds=30,max_output_bytes=32768),coding_autonomy=dict(enabled=True,max_model_requests=18,max_tool_calls=64,max_patch_write_attempts=3,max_command_attempts=3,max_no_progress=4,max_task_seconds=900),coding_git_workflow=dict(enabled=True,undo_enabled=False),web_streaming=True,web_steer=True,context_tool_result_max_chars=16000,context_max_chars=120000,max_react_steps=18,max_completion_tokens=1800,context_token_budget={'mode':'estimate','input_limit':32000})
def contract():return dict(version=1,baseline=BASELINE,authorization=AUTHORIZATION,required_authorization=REQUIRED_AUTHORIZATION,batch=str(BATCH),port=PORT,cases=LIMITS,global_limit=18,message=MESSAGE,allowed_paths=ALLOWED,final_required_paths=ALLOWED,public_command=COMMAND,command_approval='independent one-call real WebApproval; Live operator never approves; timeout/deny/unattended means no command/no strict PASS',stream=True,include_usage=True,sdk_retries=0,models={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'},tool_names=sorted(TOOLS),autonomy=config_for(Path('/private/tmp/contract-only'),dict(model='unused',base_url='http://mock.invalid')).coding_autonomy,input_limit=32000,tool_result_max_chars=16000,context_max_chars=120000,output_reserve=1800,timeout_seconds=90,web_task_seconds=1200,summary=False,judge_llm=False,MCP=False,skills=False,git_remote=False,host_score='existing Seatbelt isolated run_suite, post-turn only, no output to model',source_integrity='native Journal + exact bytes/hashes and revision chain, full protected images and Git metadata, no reset/replay',scoring=['model_workflow','patch_committed','scope','preview_receipt','current_revision_tests','controller_verified','public_tests','independent_acceptance','git_journal','tool_authority','human_command_approval','stream_protocol','request_usage','cleanup','task_correctness'],stop='one Attempt; no rerun; unknown side effects/request/metadata HALT, cleanup remains permitted',cost=None)
def plan_hash():return hashlib.sha256(json.dumps(contract(),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
