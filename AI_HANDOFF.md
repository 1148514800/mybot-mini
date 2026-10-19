# AI_HANDOFF

## 当前目标与状态

Phase24 Medium预览错误诊断与有界恢复完成，离线回归通过。分支codex/phase-24，基线192fcbd；不付费Live、不Push/Merge、不进入25。main3461dc7、用户文件app.py/USER.md、原Index、配置、已有报告及Tag/ZIP哈希核对未变。

## Medium诊断事实与限制

已有报告runs/coding_benchmark/live-20261019T145243-391f3475.json：csv-export-001、coco/deepseek-v4.1-flash，请求5次、工具9次（list_files3/read_file5/apply_patch1），read_file_range0；首个Dry Run失败，无写入/测试，blocked，stop_reason=patch_failed_without_safe_recovery，stale0。原Trace把Patch错误都归other_tool_error且未保留参数，无法还原具体拒绝原因，不能断言一定是Schema/重叠/无效变化，也不能声称本修复必然解决该次具体Patch。

## 修复与安全边界

原_RETRY三项stale_file_hash/anchor_not_found/ambiguous_context保持。新增独立预览纠正集合仅invalid_arguments/overlapping_edits/no_effective_changes，严格要求dry_run is True、validation/preflight阶段、未尝试发布；清理异常覆盖safe_to_retry=false。正式write请求上述三类仍阻断，非法路径/权限/元数据/未知及资源错误不开放恢复。无法解析JSON且无可信模式仍阻断。

增加固定failure_phase：参数解析/校验/只读预检/Diff/写入准备/发布/清理/Journal；不能凭preflight_failed就断言从未产生暂存字节。发布失败且回滚成功仍blocked；回滚冲突/状态不确定仍execution_uncertain。Controller原生safe_to_retry判定与预算不变，无宿主自动重放；同一错误重复受max_no_progress等原限制。

CodingTrace仅固定白名单代码、状态/阶段枚举和布尔值；未知映射other_patch_error/unknown_patch_failure/unknown_patch_phase，不持久化源码、Patch、参数或异常正文。通用旧Trace不改。自主提示明确任何预览/写入前用read_file_range取真实file_sha256，错误后检查反馈、重新读取再生成，不猜哈希。

此前终端审批/动态命令超时提示和30秒上限、Judge与Agent工作流独立报告保留。Benchmark/Reference/Gold/隐藏测试、Judge及命令/审批/Seatbelt实现未改，未扩大预算。

## 验证

新增11项：预览三类与原stale/anchor错误无写入证明；正式写入/后续阶段不扩恢复；3条重新读取纠正→预览→提交→真实测试→Judge；重复错误预算；非法路径/敏感访问/权限；发布及回滚异常；畸形JSON保守拒绝；白名单/源码参数异常哨兵不泄露。未删除或修改既有安全断言。

针对性11、Phase24专项131、Patch55、自主编码80及编译通过；uv run python -m scripts.check_phase全量881通过（原870+11），原Phase1/2断言通过。日志/tmp/phase24-preview-full.log。

## 归档与下一步

学习与状态转换见docs/phases/phase-24.md第17节；原phase-24 Tag/ZIP不动且不含后续修复，以当前分支后续Commit为准。等待用户明确授权后才做真实复测，新分类不能追溯旧other_tool_error。区分安全拒绝与可纠正预览输入错误，不为Medium成功率改Gold或评分，不自动推进Phase25。
