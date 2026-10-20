# AI_HANDOFF

## 当前目标与状态

Phase24 run_command cwd契约说明修复完成，基线codex/phase-24 / f20999c，离线回归通过。生产修改只涉及工具description、cwd Schema文档注解及Controller提示；路径校验、审批、沙盒、Loop与证据语义不改。本轮不付费Live、不Push/Merge、不进入25。

## 根因证据与限制

报告runs/coding_benchmark/live-20261020T141547-afa40771.json：coco2/gpt-6-astra，7次请求全部成功，预览/提交各1次，三文件修复经Judge公开2/2、隐藏4/4通过；第7次run_command审批前invalid_cwd，Agent blocked、测试0次、revision1/last_verified_revision=null。未出现审批或启动测试进程。报告无原始cwd，不能猜具体非法参数；Judge修复成功不等于Agent工作流成功。

Schema原本仅说明cwd字符串长度，Controller未解释合法形式，属于契约描述缺口，未发现放宽路径校验的依据。cwd可选，省略用`.`工作区根；显式值须是已有安全相对目录。绝对路径、..片段、内部/外部或中间符号链接、缺失目录与文件继续拒绝，敏感路径保留原共享策略。

## 修改与安全决定

mybot/tools/run_command.py补充工具说明、cwd description/default="."；mybot/agent/coding_controller.py提示优先省略cwd，禁止宿主项目/临时评测绝对路径、..和符号链接。default仅文档注解，不注入或修正参数，Schema类型/长度、required与有效输入包络不变。RunCommandTool所有方法AST保持相同，包括_cwd、execute、审批后复检和失败结果。

非法cwd仍在审批/进程前拒绝并command_fatal停止，不自动修正或重试；同批后续工具停止且ID配对。真实TTY通道、30秒命令上限、Seatbelt、Journal、Patch版本/原子性及当前revision/文件哈希测试证据检查均保留。通用提示不含案例答案，Trace不增加原始参数。

## 测试

新增9项：命令4（契约/输入范围，省略与`.`真实沙盒unittest，src真实unittest，非法路径审批前拒绝）；自主编码3（通用提示、fatal/配对/隐私、显式`.`测试后revision与哈希失效）；评测2（省略cwd完整链路、Judge通过但非法cwd仍blocked且不泄露参数）。三个测试文件原有284项方法AST比对不变。

针对性9、命令62、自主编码97、Phase24评测134项及Python编译通过；uv run python -m scripts.check_phase全量905项通过（原896+新增9），原Phase1/2断言亦通过。日志/tmp/phase24-cwd-full.log。安全回归验证超时、拒绝、真实TTY/Seatbelt失败、执行不确定及审批后目录变化仍严格停止；Git工作流101项通过。

## 配置、文档与下一步

学习说明见docs/phases/phase-24.md第19节。评测工作树当前有效配置为coco2/gpt-6-astra，忽略的config/config.json独立于主目录，本轮不改配置/凭证/端点。最近Live用90/600/900秒请求/任务/总超时，仅是该次命令参数，不是永久默认。

Benchmark/Gold/Reference/隐藏测试、Judge、预算均不改；main3461dc7、原用户修改与Index、既有报告及Tag/ZIP保留。旧phase-24归档不包含后续修复，禁止移动Tag或覆盖ZIP。

离线通过仅证明路径契约和原执行机制可用，不代表真实模型一定遵循提示。下一次Live需用户另行授权，可继续gpt-6-astra；先核对实际配置与用户给定超时/预算，不自动复测、不放宽非法cwd、不把Judge hidden_pass写成Agent verified。
