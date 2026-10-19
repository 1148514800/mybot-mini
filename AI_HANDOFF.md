# AI_HANDOFF

## 当前目标与状态

Phase24 Live命令超时配置约定修复完成，离线回归通过。分支codex/phase-24，修复基线89a3737；本轮无付费Live，不Push/Merge、不进入25。原main3461dc7、用户app.py/USER.md、原Index、配置、已有Live报告及全部Tag/ZIP哈希核对未变。

## 最新Live事实

已有报告runs/coding_benchmark/live-20261019T142215-f2814615.json：coco / deepseek-v4.1-flash，config-default-001请求8次、工具11次，Patch预览/提交各1次；Judge公开2/2、隐藏4/4通过，verified_repair_success=true，但Agent blocked，stop_reason=timeout_exceeds_configuration，真实Agent测试0次。原顶层failure=null掩盖工作流停止原因。报告没有原始参数，不能断言模型具体请求秒数。本轮未复测真实模型。

## 修复与安全约定

Phase24单命令最大/默认30秒保持。原Schema通用上限60秒误导模型：RunCommandTool现在独立实例Schema以实际配置设置maximum/default并建议省略timeout_seconds，保留原类级输入范围与host严格拒绝检查。超配置请求不截断、不扩限、不自动重试，原错误分类保留，参数名/类型/必填项不变。Controller每轮从原生工具settings动态输出command_timeout_seconds，区别任务/API超时，建议省略参数使用安全默认值。

新增每案例agent_workflow_success，以及聚合agent_workflow_success_cases/agent_blocked_count。保留Judge修复含义与评分规则；Agent blocked时顶层failure保留停止原因，即使Judge修复成功。离线明确验证两组事实可以同时成立。

上一轮终端审批输出通道和SHA提示保留：Agent原始输出仍捕获，审批检查真实stdin/绑定输出TTY、每次人工yes；不回退/dev/tty，不自动批准，非交互拒绝。Seatbelt、Patch校验、MCP审批、Benchmark/Reference/Gold/隐藏测试未改。

## 验证

新增4项：1/7/30/60配置与Schema/提示一致且互不污染；超限31/60审批前拒绝、不截断且旧非法参数分类保留；合法30秒通过真实PTY逐次审批+Seatbelt+unittest；Judge通过但超时blocked的独立报告/保存。既有省略超时终端链路加强断言；旧Schema固定60断言改为实际上限和其余结构不变检查，没有删除旧用例。PTY及模拟输入仅用于离线合成模型测试。

针对性5项、Phase24专项120、命令58、自主编码80及编译通过。uv run python -m scripts.check_phase全量870通过（866既有用例+4新增），原Phase1/2断言通过。日志/tmp/phase24-timeout-full.log。

## 归档与下一步

原phase-24 Tag仍指3f53b05，ZIP不含后续修复，不移动Tag、不覆盖ZIP；修复以分支后续Commit为准。根因与学习见docs/phases/phase-24.md第15～16节。离线验证消除配置/描述不一致，但模型仍可能主动传超限值，此时应拒绝。等待用户确认后在真实交互终端复测A；逐次审批仍必需，A正常且另获同意后才B，不自动扩大或开始Phase25。
