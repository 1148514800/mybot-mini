import hashlib,json
from dataclasses import replace
from pathlib import Path
from scripts.persistent_uat.plan import config_for as base
BASELINE='16f25f74db78089bf1bc697022e53f46473449bd'
AUTHORIZATION='NOT_GRANTED'
REQUIRED_AUTHORIZATION='GRANTED_12_REQUESTS'
BATCH=Path.home()/'.mybot-mini/uat/coding-workflow-canary-v1-20261027'
PORT=8903
LIMITS={'C01':12}
GLOBAL_LIMIT=12
ALLOWED='notesearch/search.py'
COMMAND=['python','-m','unittest','discover','-s','tests','-v']
MESSAGE='请修复notesearch/search.py中的search_notes函数。查询词先去除首尾空格，使用不区分大小写的匹配方式检查每条笔记的title或body；空查询返回空列表；结果按输入笔记的原始顺序返回id，不要排序或去重，也不要修改传入数据。只允许修改notesearch/search.py。请先阅读相关代码和测试，使用apply_patch预览后正式提交修改，再运行python -m unittest discover -s tests -v进行验证。测试未通过时不得声称修复完成。'
TOOLS={'read_file','list_files','search_code','read_file_range','git_status','git_diff','apply_patch','run_command','create_plan','update_plan','record_task_contract'}
def config_for(batch,provider):
 return replace(base(batch,provider),coding_enabled=True,coding_patch_mode='write',coding_preview_receipt=True,coding_command=dict(mode='macos_readonly',timeout_seconds=30,max_output_bytes=32768),coding_autonomy=dict(enabled=True,max_model_requests=12,max_tool_calls=40,max_patch_write_attempts=2,max_command_attempts=2,max_no_progress=4,max_task_seconds=600),coding_git_workflow=dict(enabled=True,undo_enabled=False),web_streaming=True,web_steer=True,context_tool_result_max_chars=16000,context_max_chars=120000,max_react_steps=12,max_completion_tokens=1800,context_token_budget={'mode':'estimate','input_limit':32000})
def contract():return dict(version=1,baseline=BASELINE,authorization=AUTHORIZATION,required_authorization=REQUIRED_AUTHORIZATION,batch=str(BATCH),port=PORT,cases=LIMITS,global_limit=12,message=MESSAGE,allowed_path=ALLOWED,public_command=COMMAND,command_approval='independent one-call real WebApproval; Live operator never approves; timeout/deny/unattended means no command/no strict PASS',stream=True,include_usage=True,sdk_retries=0,models={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'},tool_names=sorted(TOOLS),autonomy=config_for(Path('/private/tmp/contract-only'),dict(model='unused',base_url='http://mock.invalid')).coding_autonomy,input_limit=32000,tool_result_max_chars=16000,context_max_chars=120000,output_reserve=1800,timeout_seconds=90,web_task_seconds=900,summary=False,judge_llm=False,MCP=False,skills=False,git_remote=False,host_score='existing Seatbelt isolated run_suite, post-turn only, no output to model',source_integrity='native Journal + exact bytes/hashes and revision chain, full protected images and Git metadata, no reset/replay',scoring=['model_workflow','patch_committed','scope','preview_receipt','current_revision_tests','controller_verified','public_tests','independent_acceptance','git_journal','tool_authority','human_command_approval','stream_protocol','request_usage','cleanup','task_correctness'],stop='one Attempt; no rerun; unknown side effects/request/metadata HALT, cleanup remains permitted',cost=None)
def plan_hash():return hashlib.sha256(json.dumps(contract(),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
