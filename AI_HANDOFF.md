# AI_HANDOFF

## 当前目标与状态

Phase24首次Live反馈的两处修复已完成，离线回归通过，待用户确认后重新测试案例A。分支codex/phase-24，修复基线571e7d8。本轮不Push/Merge、不执行付费Live、不进入Phase25。main3461dc7、用户app.py/USER.md、原Index、真实配置、已有Live报告及全部Tag/ZIP已核对哈希未变。

## 首次Live事实

既有忽略报告runs/coding_benchmark/live-20261019T134803-ec1eaddc.json：coco / deepseek-v4.1-flash，config-default-001请求6次、工具9次、Token15991（输入15410/输出581），价格缺失故估价null；read_file四次、read_file_range零次、Patch写入一次stale_file_hash、命令一次审批拒绝；最终blocked，公开通过但隐藏失败，无修复。含Harness审批缺陷，不能全部归因模型能力。此前“真实模型从未调用”只适用于原归档时点。

## 修复与架构决策

run_task保留全局stdout捕获以保护原始Agent/工具输出；Live审批在捕获前绑定原调用者输出。cli_command_approval增加host-only可选output参数，提示与flush发到该通道，仍检查真实stdin和所选输出TTY；每次人工精确yes，不缓存，不回退__stdout__/dev/tty。默认调用方与MCP安全语义保留，Seatbelt未改。

仅给CodingTaskController自主编码提示补充read_file_range的metadata.file_sha256→expected_sha256、不得猜哈希、建议Dry Run、stale后重新读取重建。SHA是完整原始文件字节，非编号片段。Patch校验、工具参数Schema、旧读取模式、Gold均未改。

## 验证

新增7项全过：真实PTY离线原Loop/Controller/Journal/Judge审批与拒绝，逐次yes、非交互拒绝、Offline无SDK且保护输出、全文件SHA/旧模式、错误SHA重新读取预览再写入和真实测试。PTY及模拟输入仅用于离线测试，未用于付费Live。

Phase24专项116、命令58、自主编码80、MCP审批25和编译通过；uv run python -m scripts.check_phase全量866通过（原859+新增7），原Phase1/2断言通过。日志/tmp/phase24-fix-full.log；无凭证/原始工具正文泄露哨兵，Index/Journal与独立Judge兼容。

## 归档与下一步

phase-24仍指原3f53b05，原ZIP不包含本次修复，不移动Tag、不覆盖ZIP；修复以本分支后续Commit为准。学习及根因见docs/phases/phase-24.md第15节，索引已更新。用户确认后再在真实交互终端运行案例A，保留逐次命令审批；A正常且另获同意后才能B。本轮离线通过不证明真实模型已修复成功；不自动重跑付费测试，不改评分或Gold。
