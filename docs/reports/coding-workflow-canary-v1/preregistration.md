# C01唯一预注册

LIVE_AUTHORIZATION: NOT_GRANTED

基线16f25f74db78089bf1bc697022e53f46473449bd；分支codex/coding-workflow-canary-v1；唯一新批次~/.mybot-mini/uat/coding-workflow-canary-v1-20261027/；固定127.0.0.1:8903。未来只接受新的精确GRANTED_12_REQUESTS，且原命令仍需真人逐次WebApproval。旧2次及任何历史余额不继承。

唯一任务原文（不得追加、改写或重发）：

> 请修复notesearch/search.py中的search_notes函数。查询词先去除首尾空格，使用不区分大小写的匹配方式检查每条笔记的title或body；空查询返回空列表；结果按输入笔记的原始顺序返回id，不要排序或去重，也不要修改传入数据。只允许修改notesearch/search.py。请先阅读相关代码和测试，使用apply_patch预览后正式提交修改，再运行python -m unittest discover -s tests -v进行验证。测试未通过时不得声称修复完成。

原生调用链create_app→ChatRuntime→AgentLoop→CodingTaskController→ToolRegistry→ProviderFailover→AsyncOpenAI Streaming。主coco/deepseek-v4.1-flash，备coco2/glm-5.3-flash；stream/include_usage=True、SDK retries0。coding enabled/write/preview_receipt/read_only，command macos_readonly，autonomy/git_workflow开启、Undo关闭；MCP/Skills/语义摘要/JudgeLLM关闭。实际原生Schema保留（含read_file和create_plan等元数据工具），不编造接口。

12全局/Case物理请求、单Attempt；ReAct12、工具40、写尝试2、命令2、无进展4、任务600秒、命令≤30秒/32768字节、Web900秒。输入估算上限32000、输出预留1800、上下文字符120000、单工具结果16000，窗口真实上限未知；不修改预算求通过。原只读14k无法容纳Coding Schema，所有参数在冻结前固定并受原预算门执行。

文件范围仅notesearch/search.py。先读真实SHA，原生dry_run预览、Receipt Commit和Journal，禁止绕过Patch或shell写入。注册命令唯一python -m unittest discover -s tests -v，cwd '.'，有效Python路径由原RunCommand验证并在UI完整显示。拒绝/超时/无人批准不执行、不自动批准或重复请求，不由模型额度代替批准。

Public5/Host10及Fixture/Gold/Reference代码hash随源码、prepared hash冻结。模型看不到Host目录或结果；验收仅Turn结束后在现有verified Seatbelt子进程运行，失败自检BLOCKED，无宿主import。每请求核验不可变资产、Git metadata、实际Diff与完整Native Journal修订链；只接受可证明的合法修改，未知变化/HALT/执行不确定阻止继续，不reset/checkout/重新prepare。

15维独立评分见plan.contract与score.assess：工作流、真实Patch、范围、Preview/Receipt、当前Revision测试、Controller、Public、Host、Git/Journal、Authority、真人审批、Streaming、预算Usage、资源清理、用户任务正确性。Strict需全部成立；Synthetic批准不等于真人、Controller verified不等于独立正确。无可信价格cost=null；Mock Token不冒充供应商Usage。

离线完成实现/验证→Implementation→本Preregistration→干净工作树唯一prepare/freeze/verify→Acceptance→Push/远程核对→再verify。freeze后源码/Fixture/Host套件/评分不变。未来Live前原verify、新隔离Chrome/端口/Lease/两库/空账本核验，操作器仅DOM发消息，真实命令由实际用户确认；不补跑、不额外Judge、不使用旧账本。未知请求/Side Effect/权限/完整性立即停止，保留HALT且只清理可确认资源。

原Phase25、R01/D01/D02/T01/T02/T03/N01/N02与旧私库、main/Tag/ZIP/用户Chrome/8765/共享AppleDouble不修改。真实结果另存live-results/execution-01，不改本离线报告。
