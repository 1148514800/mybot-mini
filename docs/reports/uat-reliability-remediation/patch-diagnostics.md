# Patch 与只读活动诊断

原工具结果保留，新增常量白名单字段 error_category、safe_error_code、failure_phase、operation_intent、file_metadata_supported、guidance_code。safe_to_retry 透传原执行器决策，不以观测逻辑改变原控制行为。阶段区分 argument_parsing、validation、preflight、preview、write_preparation、publication、cleanup、journal；无法确定时 unknown。

unsupported_ownership 不再仅能看到兼容字段 metadata_changed；Web显示精确安全码、阶段、意图和文件属组检查建议。unsupported_metadata 使用ACL/xattr/mode建议。已发生发布或不确定执行使用 inspect_state_no_replay，不能声称没有写入。参数解析异常无法恢复可靠意图时一律 unknown，无 dry_run=True 猜测。底层有界JSON解析器将多种失败统一 invalid_arguments，本轮保留这个事实，不假称能区分 malformed_json。其他不在常量集合的错误映射 unknown，不回显异常正文。

原生工具 exact type gate 后仅将这些字段送入 tool_finished；失败事件无Patch正文、Receipt、nonce、原始参数或主机路径。既有成功Preview的有界脱敏Diff功能保留，不能将其当正式提交。MCP不获得本地读取路径展示能力。

read_file/read_file_range 成功时，使用 RepositoryTool.resolve 的工作区和敏感路径策略重新验证后，才展示相对路径；行范围、截断、next_start_line/更多行来自真实返回元数据。无法验证路径则省略全部此类展示信息，不将完整参数透传到Web。

真实内置浏览器访问127.0.0.1:8879，使用合成Client和明确的原生元数据错误注入；真实发送、HTTP/SSE、展开卡片均通过。显示 unsupported_ownership / preflight / preview、属组建议，最终执行失败、revision0、修改0、有效测试0，无审批。截图：[离线诊断卡片](patch-diagnostic-browser.jpg)。Chrome自动化导航带cross-site被正常拒绝；内置浏览器正常访问，未修改同源防护。

```bash
uv run python -m scripts.check_patch_diagnostics
uv run python -m scripts.check_remediation_e2e
uv run python -m scripts.check_remediation_e2e --serve-diagnostics
```

U05历史错误仍unknown。新码只能改善未来诊断，不能恢复未保存的历史证据。
