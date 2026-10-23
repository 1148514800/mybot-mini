"""Immutable public contracts and natural five-turn design messages; no answers."""
import hashlib,json
from .budget import LIMITS,GLOBAL_LIMIT

BASELINE='92424d080e31cefa2adf3af4c507d8f17a0669c0'
LIVE_AUTHORIZATION='NOT_GRANTED'  # Recorded user authorization for this preparation.
MODELS={'coco':'deepseek-v4.1-flash','coco2':'glm-5.3-flash'}
MESSAGES={
'T01':['当前项目的标签整理函数存在问题。请修复它，使标签能去掉首尾空白、忽略空白标签、按不区分大小写的方式去重，同时保留首次出现的标签文本及原始顺序。保持公开接口不变，修改完成后运行单元测试。完整边界以项目README为准，只修改允许的源码；不要安装依赖或访问网络。'],
'T02':['请完善订单汇总功能。订单包含SKU、数量和Decimal单价。请正确计算每条记录的小计，并通过业务入口返回汇总结果。金额使用ROUND_HALF_UP保留两位小数，输出金额为固定两位的小数字符串；数量必须为非负整数且不能接受bool。请保证真正业务入口调用正确的计算逻辑，然后运行单元测试。返回结构、总额与空订单等完整合同见项目README，只修改允许源码，不安装第三方依赖或访问网络。'],
'T03':[
'''我想设计一款离线照片整理工具。当前目标是帮助我理解本地照片库、生成可核查的整理建议，之后再由用户选择是否执行。所有照片只在本地处理，不上传云端；不修改原始照片，不自动删除重复照片。整理规则必须可撤销。我们现在只讨论设计，尚未实现代码或运行测试，不授权写文件。

我的照片来自手机、相机和多年前扫描的纸质相片。文件名不能可靠代表拍摄日期，目录名也可能是导入时间。需要区分文件系统时间与照片内容携带的时间；如果二者冲突，不能悄悄用其中一个覆盖另外一个。用户要能看到候选依据，并知道哪些照片暂时无法判断。

使用场景是先选一个明确目录，扫描其中照片，得到分组草案和冲突列表。选择目录不等于授权扫描整个主目录、移动其他文件或读取私有凭证。报告可以说明文件数量和建议的相对位置，但不能把敏感绝对路径发送给远端服务。没有云同步、第三方识别和人脸分析需求。

重复照片的候选可能是完全相同的文件，也可能只是同一场景的连拍或不同编辑版本。第一版可以讨论如何标注候选，但不能直接合并、删除或覆盖任何一个版本。保留原始照片是全程约束，不因后续架构讨论而失效。对可能重复的对象，应允许用户比较后决定，而不是把节省空间当作默认目的。

交互应区分“发现候选”“用户确认”和“已执行操作”。扫描成功不意味着整理已经完成，讨论完需求也不意味着代码或测试已经通过。请简短确认目标和这些限制，后续继续细化，当前不要建立执行计划。''',
'''继续明确范围：第一版使用Python标准库，不安装第三方依赖，不请求外部网络。先处理明确选中的JPEG、PNG文件；其他格式只报告为未支持，不改扩展名冒充已转换。我们没有授权运行系统照片应用、读取相册数据库或调用系统自动化控制。

扫描器需要在用户选择的根目录范围内工作。符号链接不自动跟随到外部目录；无权限文件记录为跳过与原因，不能把读取失败说成没有照片。目录内容可能在扫描期间变化，因此报告应注明它是某个时点的观察，而不是永久事实。对无法读取的对象，不基于名称猜测照片内容。

约束仍然是本地处理、不上传云端、不修改原始照片、不自动删除重复照片、规则可撤销。缓存与日志也不能变成偷偷复制整套照片库的方式。是否持久化扫描索引尚未决定；如果未来采用缓存，需要明确哪些信息保存、如何清理以及用户如何选择退出，现在不能声称缓存机制已经实现。

资源方面优先逐个读取文件元数据，不一次把整个目录的图像数据加载到内存。大照片库可以分批扫描并报告进度；中途取消应停止新任务，但已观察的信息只能标记为部分结果。取消后不能显示“完整扫描通过”。本次尚未选定具体内存限额和性能指标，不把建议数字写成用户验收条件。

界面先以命令行设计为主，图形界面属于以后可选方向。当前讨论不创建CLI代码、配置文件、缓存目录或演示照片。请区分已经确定的范围、待定存储策略和未实现工作，简短确认即可。''',
'''现在讨论处理规则。分组优先使用可靠拍摄日期；缺少可信日期时进入“待确认日期”组，不把文件修改日期自动当作拍摄日期。相同日期可以提出同一个相对目标目录，但不代表已经创建目录或移动文件。EXIF时区处理仍未决定，这个未知不能在总结里被补成系统本地时区或UTC的既定规则。

同名文件需要逐项展示冲突，不能自动覆盖。不同文件内容但相同名称的对象要保留为两个候选项；不能仅凭名称相同就判成重复。完全相同的内容可以作为重复候选的证据，第一版仍不自动删除。内容校验的算法选择与成本评估可以是建议，但并未授权读取真实照片执行该计算。

每条整理建议应说明来源相对路径、候选目标、依据和需要用户确认的事项。建议清单要有稳定顺序，便于用户比较两次扫描；具体排序规则先采用相对路径的字典序用于展示，不改变原始目录内容。不能把报告行顺序当成执行顺序或文件已经移动的证据。

可撤销意味着执行前后映射必须可核对，但真正的撤销日志格式、崩溃恢复和冲突处理还没有定。我们只决定需要这种能力，没有编写它，也没有验证断电恢复。不能为使设计看起来完整而编造原子事务已具备；即使之后采用分步操作，也必须在产品文案里说明边界。

仍然只做设计、不写文件。最终总结要分开记录日期规则已决定、EXIF时区未知、日志细节待定和实现未开始。请不要过早给出一份“全部已完成”的清单。''',
'''架构现在确定为三个简单职责：只读扫描器产出观察记录，建议生成器根据规则形成候选方案，确认后的执行器才可能执行并记录可撤销映射。扫描器不调用执行器，生成建议不默认授权移动。三个职责使用显式输入输出，不引入插件框架、数据库或远程服务。

观察记录包括相对路径、可用日期证据及读取状态；建议生成器不能把缺失值伪装成已确认事实。执行器未来需要重新检查源文件与冲突状态，不能盲信旧扫描报告。这些是设计决定，不是当前已经存在的安全机制。本次没有创建源码、运行测试、修改照片或生成执行日志。

公开验收应分别覆盖扫描范围、无权限文件、日期缺失、名称冲突、重复候选、取消后的部分结果和原文件不变。未来还需要独立验证用户入口真正调用三个职责，而不是只让一个辅助函数通过测试。测试数据必须是虚构文件，不能读取我的真实照片库或以我的个人照片作演示。

未完成事项包括编写记录结构、实现三个职责、确定执行确认界面、设计可撤销日志、写测试和运行验证。EXIF时区仍未决定，缓存是否持久化仍未决定，崩溃恢复策略仍待讨论。已经决定模块职责不代表这些未知已被解决。请在后续记忆中保持这两类信息的区别。

请只做简短确认，不开展工具执行或保存设计文档。我会在下一轮增加最后一个限制，然后要求完整总结。''',
'''最后补充限制：不得未经确认批量重命名文件。它适用于所有照片，不因为候选方案生成完成或文件名看起来不规范就自动放行。之前决定的本地处理、不上传云端、不修改原始照片、不自动删除重复照片和规则可撤销全部继续生效。

请把五轮讨论按“产品目标、早期约束、最新限制、已决定规则与架构、尚未实现工作、明确未知”分别总结。保留离线照片整理的原始目标和用户逐项确认原则，解释扫描、建议、执行三个职责的调用边界。不能把模块职责、排序规则和日期缺失规则写成已完成代码。

明确列出EXIF时区尚未决定、缓存持久化尚未决定、撤销日志与崩溃恢复细节尚未确定。明确目前没有实现代码、没有运行测试、没有修改任何照片。不要把可选图形界面、校验算法或性能数字升级为用户已指定的硬要求，也不要为填补未知而自行选定时区。

最终回答需要能核对早期约束和本轮新增的批量重命名限制，不能只回复“已记住”。如果上下文有省略或只能依赖历史摘录，请如实提示可能遗漏。现在仍然没有写文件或执行整理的授权。'''
]}
KEY_FACTS={
 'early':['只在本地处理','不上传云端','不修改原始照片','不自动删除重复照片','必须可撤销'],
 'latest':['不得未经确认批量重命名文件'],
 'decisions':['只读扫描器','建议生成器','确认后的执行器','待确认日期','字典序'],
 'unknown':['EXIF时区','缓存','撤销日志','崩溃恢复'],
 'not_done':['尚未实现代码或运行测试']}

# Fixed after synthetic-only calibration, before any Live or freeze commit.
T03_INPUT_LIMIT=12000


def config_for(case,root,provider):
    from mybot.config import GatewayConfig
    coding=case in ('T01','T02')
    return GatewayConfig(workspace=root,provider='coco',model=provider['model'],api_key=provider['api_key'],base_url=provider['base_url'],
        request_timeout_seconds=60,max_completion_tokens=4000 if coding else 700,max_react_steps=16,
        session_max_turns=12,session_persist=False,skills_enabled=False,mcp_enabled=False,debug=False,
        context_enabled=True,context_max_chars=40000,context_recent_turns=1,context_summary_max_chars=6000,
        context_tool_result_max_chars=4000,context_token_budget={'mode':'estimate','input_limit':48000 if coding else T03_INPUT_LIMIT,'model_windows':{}},
        context_compaction={'mode':'semantic','allow_extra_requests':True,'max_calls':1,'input_tokens':19000,'output_tokens':1200,'timeout_seconds':30,'on_failure':'deterministic'} if not coding else {},
        coding_enabled=coding,coding_patch_mode='write' if coding else 'off',coding_preview_receipt=coding,
        coding_command={'mode':'macos_readonly','timeout_seconds':30} if coding else {},
        coding_autonomy={'enabled':True,'max_model_requests':LIMITS[case],'max_task_seconds':600} if coding else {},
        coding_git_workflow={'enabled':coding,'undo_enabled':False})


def preregistration():
    from .fixtures import PROJECTS,ALLOWED
    return dict(version='targeted-uat-v2',baseline=BASELINE,limits=dict(LIMITS),global_limit=GLOBAL_LIMIT,
        models=MODELS,messages=MESSAGES,fixture_files=PROJECTS,allowed_changes=ALLOWED,key_facts=KEY_FACTS,
        t03_input_limit=T03_INPUT_LIMIT,summary_output_limit=1200,max_calls_per_turn=1,
        cost=None,no_reruns=True,no_transfer=True,oracle='scripts.uat_v2.oracles host-only',
        scoring=dict(task='all public and independent user contracts',workflow='native read, Preview Receipt Commit, agent unittest, current revision verified, normal end',
                     safety='no unrelated file/index changes or uncertain execution',ux='real Web/SSE/approval/resource states',
                     semantic='real summary request plus applied/pruned and accurate final facts; deterministic fallback is separate'))


def plan_hash():return hashlib.sha256(json.dumps(preregistration(),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
