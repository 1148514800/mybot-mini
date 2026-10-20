# AI_HANDOFF

## 当前目标与状态

Phase24 apply_patch预览到提交契约优化完成，基线codex/phase-24 / 946ac20，离线回归通过。仅补充模型可见说明及离线测试，不真实LLM、不付费Live、不Push/Merge、不进入25。生产修改仅mybot/tools/patch.py description/parameters注解和mybot/agent/coding_controller.py instruction。

## 历史证据与未知范围

runs/coding_benchmark/live-20261020T145953-eb85cef0.json：error-retry-001、coco2/gpt-6-astra，11次请求全响应、21次工具、4次计划独占响应；第10次预览成功，第11次正式写入invalid_arguments，failure_phase=validation、safe_to_retry=false。Agent blocked/patch_failed_without_safe_recovery，无提交/测试，revision0；Judge评估未修改基线。报告无原始参数，不能认定预览和提交changes相同或定位具体错误字段，不能据隐藏失败判定预览修复错误。

原Loop有界JSON解析失败使用argument_parsing；validation是工具本地有界/Schema校验阶段，尚未文件预检。write_preparation可能已有暂存/备份/Journal写入，publication后需原恢复流程；不能混淆阶段或仅凭preflight_failed断言完全无副作用。Schema结构本来完整，改进点是预览到提交使用说明，未证明文档缺口必然导致那次错误。

## 最小修改与安全规则

工具说明列明update/op/path/expected_sha256/edits、edit/old_text/new_text、add/op/path/content及禁止多字段；dry_run说明true仅预览、false显式请求写入且需patch_mode=write；changes说明目标与内容未变时复用同一结构，仅切换dry_run=false，改动changes须重新预览。Controller补充同样通用规则，不含案例答案。

既有DIRECT/PLANNED、批处理及临近预算优先修复/真实测试/审查提示已覆盖，不重复叠加或改Planning。没有自动缓存/重放预览、修正非法参数或新增工具状态；合法直接写入旧行为保留。

完整嵌套Schema去除新增description后与基线一致；Patch模块除description/parameters外AST相同，Controller除instruction外AST相同。_RETRY三项stale/anchor/ambiguous和独立预览纠正规则不变；正式写入invalid_arguments仍safe_to_retry=false且严格停止。SHA、路径/权限、原子发布/回滚、Journal、Revision、真实测试证据、审批/Seatbelt及预算均不改，Trace只保留固定分类不存原参数。

## 离线验证

新增11项：Patch6（说明、同changes的update+add预览/写入、预览无修改且不启用写权限、非法dry_run、必填/额外/edits/SHA/数量、预览后stale重新读取）；自主编码3（通用契约及原预算指令单份、提交后需真实测试、非法写入fatal且文件/Index/Revision/Journal不变）；评测2（同changes完整验证、预览后多字段拒绝与敏感哨兵不入报告）。负例是合成错误类别，不是历史载荷还原。原三个测试文件286项方法AST不变。

针对性11、Patch61、自主编码100、Phase24评测136及Python编译通过；uv run python -m scripts.check_phase全量916项通过（原905+新增11），原Phase1/2断言亦通过，包含真实TTY审批、Seatbelt及Git工作流101项安全回归。日志/tmp/phase24-patch-contract-full.log。

## 配置、文档与下一步

详细学习与阶段表见docs/phases/phase-24.md第20节。配置仍为评测工作树独立忽略文件中的coco2/gpt-6-astra，不改凭证/端点；近期Live用90/600/900秒仅为当次请求/任务/总超时参数，不是永久默认。最近parse-convert-001在946ac20已完整verified/hidden_pass；error-retry-001仍未提交修复。

Benchmark/Fixtures/Gold/Reference/隐藏测试、Judge、预算不改；main3461dc7、原用户文件及Index、历史报告、全部Tag/ZIP保留；旧phase-24归档不含后续修复，禁止覆盖或移动。下一次error-retry-001 Live须用户另行授权，可保持原模型与预算；离线通过不保证真实模型遵循changes复用说明，不自动重跑、不扩大正式写入重试白名单。
