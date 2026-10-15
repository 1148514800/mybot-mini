# AI Handoff

## 当前状态

Phase 11 MCP Tool Permissions / Human-in-the-Loop 功能与离线验证完成，阶段提交后在干净独立工作树执行 phase-11 归档及独立还原验证；结果由后续交接提交补记。Phase 1–10 Tag/ZIP 不变。未调用真实 LLM API，不自动 Push，不进入 Phase 12。

## 实现与决策

- mcp_client/config.py、config.py：严格本地 tool_policies（allow/confirm/deny），键仅允许 allowed_tools；缺省 confirm；未知 mcp/Server 字段拒绝。模板 add/echo/read_note allow，save_note/delete_note confirm，MCP 仍默认关闭。不改用户真实配置。
- approval.py：冻结 ApprovalRequest、枚举批准、可注入 async provider；CLI 要求 stdin/stdout TTY，只接受本次 yes。参数 JSON 转义控制字符，完整展示上限4000；敏感遮蔽或超限则拒绝，EOF/异常/无提供者 fail-closed，不缓存批准。
- manager.py：隐藏 deny 工具，直接 Adapter/Manager 调用同样受控；owner Task、allowlist/策略快照、Schema 校验、冻结参数、批准之后才调用 SDK。沿用 SDK 2.3.0 连接生命周期；不在子 Task 进入/退出 Client。最近256条内存审计只记录元数据，不持久化正文/原始异常。
- loop.py：拒绝后不再请求模型重试；本批剩余调用全部补失败结果但不执行，配对完整，正确关闭 Plan 和持久化轮次。原生工具语义未改，/clear 不改变策略、不清空远端笔记、不复用授权。
- demo_server：内存 save_note/read_note/delete_note，key 1–100、content≤2000、≤100条，无文件/网络/Shell；重启清空。scripts/check_approval.py 与 check_phase 集成，Phase10测试夹具显式 allow，教程/索引/README/配置模板同步更新。

## 验证

新增25项真实stdio协议+注入审批+模拟LLM测试通过，包括四种保存/删除批准与拒绝的真实远端状态、无提供者/非TTY/非法输入/EOF、deny直接调用、参数偷换、跨任务、批量停止/ID配对/磁盘轮次、Plan无成功证据、clear/重启、审计隐私、取消及PID释放、Demo边界。全量Phase1–11共156项unittest及Phase1/2断言检查通过；compileall通过；scripts.test_phase_archives归档安全集成检查通过。没有真实API请求，未进行真实模型审批流程手工验证。

## 局限与隐私

审批不是OS沙箱，可信Server启动/初始化已有用户权限。Server自身异常行为不能由客户端隔离；已发送调用超时不能证明无副作用。输入线程取消后可能仍需输入/EOF退出，SDK仍由owner清理。审计不包含参数，但Session/SessionStore仍可能保存原始参数与结果（包括拒绝的请求），没有宣称全存储脱敏。敏感字段识别有限；完整关键参数无法展示则拒绝批准。无授权缓存/远程/OAuth/审计持久化/回滚。

## 用户修改与环境

macOS+Python3.12+/uv。app.py三处用户注释与USER.md修改保留、不提交；只暂存本阶段app注入。实际配置/Session/runs不归档。ExFAT生成的._*仅识别AppleDouble头后清理，不删除其他同名文件；快照排除并在APFS临时目录验证。

## 下一步

完成此阶段提交的save_phase.sh 11与restore_phase.sh 11验证，再补记真实Commit/ZIP；不改旧归档、不进入Phase12。学习见docs/phases/phase-11.md。
