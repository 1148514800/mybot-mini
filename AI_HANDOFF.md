# AI Handoff

## 当前状态

Phase 12 stdio / Streamable HTTP 双传输已完成并独立归档；annotated phase-12 指向10b7f198c514f370e65be10ff23d1240583143b5，ZIP：../mybot-mini-snapshots/phase-12.zip。Phase 1–11 Tag/ZIP 不变。不自动 Push，不调用真实 LLM API，不进入 Phase 13。

## 实现与架构

- mcp_client/config.py：transport 缺省 stdio，按传输拒绝不匹配字段；HTTP 只接受字面量回环 HTTP 或用户本地明确配置的 HTTPS，拒绝凭证/query/fragment/控制字符/非法URL。沿用 allowlist/策略/timeout。为旧配置保留 args 缺省[]；localhost明文拒绝，使用127.0.0.1。
- transport.py：小型SDK传输工厂；stdio沿用PROJECT_DIR cwd与stderr隔离；HTTP用官方streamable_http_client+显式AsyncClient，trust_env=False、无认证/环境代理/重试，发送前移除隐式凭证。Endpoint固定，全部重定向拒绝；首次GET后禁止网络GET重连/resumption。HTTP期间抑制SDK/network正文日志，退出恢复。
- manager.py：共用原 Client(mode=legacy)/发现/原子注册/Adapter/Schema/Phase11审批/审计。owner Task进入、调用、清理不变。SDK后台HTTP错误可能先取消owner，再在aclose抛ExceptionGroup；_close收集后安全分类，不能漏出原始HTTP错误。故障关闭所有MCP，不自动重连/重试；提示远端副作用可能未知。
- scripts/mcp_http_demo_server.py：独立官方SDK HTTP Server，127.0.0.1、/mcp、精确Host/Origin防护。复用Phase11五个内存工具；默认stateful+JSON，客户端退出DELETE会话但不终止Server或清笔记。测试另外覆盖SSE与stateless JSON。
- 示例同时含stdio/http（整体仍off）；启用会连接所有配置Server，不用的条目移除。pyproject/uv.lock仅声明已有httpx2 2.13.1、uvicorn0.54直接依赖，仍41包，MCP/mcp-types锁定2.3.0未升级。AgentLoop/Approval/Adapter/Session/Context未改。

## 验证

28项真实HTTP专项通过：真实CLI启动/初始化/list/add/echo、stateful DELETE/资源释放/Server存活、SSE/stateless、双传输命名隔离/注册失败原子清理、URL及配置、审批真实笔记状态/无调用拒绝/冻结参数、Plan成功与失败证据/配对/clear、Schema预算和原文保护、isError、HTTP401/403/404/500/503、连接失败/错误Endpoint/损坏初始化/list失败、超时副作用未知且无写入重试、中途断连、取消/owner、禁代理/netrc/隐式凭证、debug与审计隐私、Host/Origin、无网络GET重连。全量Phase1–12共184项unittest及Phase1/2断言检查通过；归档安全集成检查通过。最后强化的HTTP Plan/Schema计量断言另有2项定向测试通过。未访问第三方MCP或真实模型。干净APFS工作树执行save_phase.sh 12成功；ZIP105条目，冻结安装/编译/184项回归及Phase1/2断言通过。restore_phase.sh 12独立还原后再次冻结安装、编译及全部回归通过。ZIP的Commit注释与Tag一致，不含真实配置/Session/runs、用户未提交app注释或USER修改，已发布到实际同级快照目录。

## 局限与安全

HTTPS仅基础无认证/证书校验路径，未访问实际远程TLS服务器；无OAuth/Bearer/任意Header/旧SSE/重连/回滚。HTTP仅字面量回环、所有重定向拒绝是更保守限制。SDK内部可能尝试GET恢复，但hook阻止后续网络请求；无tools/call POST重发。已发送工具超时/取消不能证明无副作用，实测写入可成功但响应超时。Server独立且跨HTTP Client共享进程笔记，非多租户、非OS沙箱；Session仍可能明文记录参数/结果。12000是适配文本上限，不是HTTP JSON内存防护；SSE用SDK默认1MiB事件上限。日志抑制为进程级临时设置，只支持当前单网关串行模式。

## 用户修改与环境

macOS+Python3.12+/uv；保留app.py原三处注释与USER.md未提交修改，Phase12不改app.py，也不改真实config/Session/runs。ExFAT的._*只在确认AppleDouble头后清理，快照排除，APFS独立验证。学习见docs/phases/phase-12.md。

## 下一步

Phase12已结束，等待用户指定下一项任务；不重复创建phase-12或覆盖ZIP，不修改旧归档、不进入Phase13。
