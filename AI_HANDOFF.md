# AI Handoff

## 当前状态

Phase10本地stdio MCP Tools已实现并专项验证，待提交/phase-10/ZIP独立归档。诊断补充ac9f823已独立提交，Phase1–9 Tag/ZIP不变。本阶段未调用真实LLM API，不进入Phase11，不自动Push。

## 实现

- mcp_client/config.py：默认off，明确command/args/allowlist/timeout，服务器数量/名称/类型校验，深复制配置；config.py与模板/本地补齐mcp段。
- manager.py：官方SDK2.3.0 Client+stdio_client，mode=legacy握手2025-11-25，固定PROJECT_DIR cwd、stderr抑制，分页发现/过滤/全部验证后注册，owner Task持有AsyncExitStack。调用异常/超时/断连关闭全部MCP，重启恢复；正常/异常/取消清理，原生工具不覆盖。
- adapter.py：mcp__server__tool唯一名称，保守Schema子集原样保留、jsonschema4.26完整参数验证；文本/structured_content/isError转换、媒体拒绝、12000字符显式截断。
- app.py在Gateway同Task建立/释放连接；loop.py只增加MCP debug参数遮蔽。原ReAct/Planning/Session/Skills协议不变。demo_server用MCPServer提供无副作用add/echo。
- pyproject/uv.lock锁定mcp/mcp-types2.3.0与jsonschema4.26；scripts/check_mcp.py、统一回归、教程/索引/README更新。

## 验证

17项真实stdio子进程+模拟LLM测试通过：默认/配置/握手/list/allowlist/Schema/多个服务器/原生冲突/参数/文本结构化媒体长结果/isError/启动失败/握手与工具超时/断连/正常异常取消释放/owner Task/Gateway/Session配对/clear/Planning/Skills/Context/debug。全量回归与编译、归档安全检查通过；独立ZIP待完成。无真实LLM调用，无第三方Server安装。

## 决策与局限

可信程序有用户权限，不受workspace沙箱；只stdio/Tools/串行，无远程/自动重连/任意env/多轮输入。$ref/$defs/oneOf/pattern等未测试Schema明确拒绝，不静默删约束；未声称所有Provider支持。SDK接收端无本项目字节级内存沙箱，12000是适配器文本上限。外部错误正文/stderr为隐私不转发，安全诊断较粗。MCP启动失败阻止CLI启动但不改原生registry；调用失败关闭MCP后原生工具仍在。不要在wait_for子任务进入SDK上下文。

## 用户修改与环境

macOS、Python3.12+、uv。app.py三处用户注释保留，仅暂存MCP变更；USER.md改动不提交；真实配置/Session/runs不归档。ExFAT ._*尽量COPYFILE_DISABLE=1，归档排除，APFS独立验证。

## 下一步

完成Phase10本地Commit/Tag/ZIP及独立还原验证，记录SHA；之后由用户指定。不要修改旧归档、不进入Phase11；学习见docs/phases/phase-10.md。
