# AI_HANDOFF

## 当前目标与状态

Phase24首次Hard失败诊断与通用Planning预算指引优化完成，基线codex/phase-24 / 5bdfb01，离线回归通过。本轮不付费Live、不Push/Merge、不进入25。生产修改仅CodingTaskController.instruction；Planning、Loop、ContextManager和工具执行语义不改。

## 诊断事实与限制

报告runs/coding_benchmark/live-20261020T044139-f6127fc8.json：validation-chain-001，coco/deepseek-v4.1-flash；请求12/12、工具20、计划管理独占5次响应（4/5/8/9/12），最后update_plan后下一请求被max_model_requests拒绝。2次预览/提交、0次Agent测试，revision2/last_verified_revision=null。仅修改normalize.py、validation.py；独立Judge公开2/2通过、隐藏未全过。必须同时承认工作流预算不足和候选代码未修复完整，不能说仅因预算失败。无API、审批、Seatbelt、Patch、Index或Journal错误。安全Trace不含参数/源码，不能还原模型动机或具体隐藏失败输入。

## 改动与架构决定

保留Phase4通用Planning和Schema。原Loop已支持顺序批处理，未增加执行权限或宿主伪造计划调用。自主提示明确清晰目标可DIRECT，多依赖可少量Plan步骤；已收到证据后可同响应completed→next in_progress→下一工具，create/start/调查亦可合并；依赖结果的参数和SHA必须等待真实返回。

动态model_requests_remaining包含当前待请求响应（instruction先于before_request）；剩余≤3时提示conserve_requests，已提交且当前revision缺测试证据时verify_current_revision。仅建议为必要修复、批准测试、结果审查留请求，不硬性保留配额、不增预算、不自动执行工具。补充通用入口→转换→验证→返回及调用方使用结果的检查，不含案例特定答案。

真实TTY逐次审批、30秒命令上限、Seatbelt、Patch SHA/原子性/恢复边界、Journal、revision测试证据和协议配对不改。Plan证据只是一般成功工具结果，不能替代Controller代码验证或独立Judge。既有预览错误白名单、审批输出通道和动态命令超时提示保留。

## 验证

新增15项：请求状态/临界点、测试及后续修订优先级、DIRECT五次与PLANNED六次响应实际修复、有效连续转换、无证据/仅预览/失败步骤拒绝、多副作用整批拒绝、低预算合成模型优先真实测试、忽略提醒仍严格停止、计划完成不能掩盖缺测试/测试失败/隐藏失败、两文件原子预检和单revision、通用提示及报告隐私。原两个测试文件211项既有方法AST比对不变。

专项：自主编码94、Planning12、Patch55、Phase24评测132全部通过；Python编译通过。uv run python -m scripts.check_phase全量896项通过（原881+新增15），原Phase1/2断言亦通过；含命令58、Git工作流101及真实TTY/Seatbelt安全回归。日志/tmp/phase24-budget-full.log。

## 文档、安全与下一步

学习说明和请求分组证据见docs/phases/phase-24.md第18节。Benchmark/Fixtures/Gold/Reference/隐藏测试、Judge、安全工具及预算未改；main3461dc7、原用户app.py/USER.md修改、原Index、既有报告、配置和全部Tag/ZIP哈希核对未变。旧phase-24归档不包含后续修复，禁止移动Tag或覆盖ZIP。

DIRECT选择、调用链提示仅提高成功机会；批处理可行性与低预算状态驱动测试有离线证据，但未改变安全状态机。新增提示增加上下文，真实Token净变化和模型遵从性未测。等待用户另行授权后才在原预算下单次Hard复测；离线通过不代表Hard真实模型成功。不要重复排查已保留的审批/超时/预览恢复问题，不扩大重试范围或预算。
