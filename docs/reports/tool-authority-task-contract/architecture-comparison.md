# 参考架构与实际取舍

查阅日期：2026-10-24。参考为公开源码，未运行上游项目、未引入框架依赖。

|参考|借鉴点|本项目落点|
|---|---|---|
|[Codex orchestrator](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/orchestrator.rs)|审批要求、策略来源和沙箱尝试分层|Registry 先拒绝，再进入原生工具自己的安全协议；不共享审批缓存|
|[Codex parallel](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/parallel.rs)|保留调用所属步骤及取消生命周期|保留已有串行批次、请求可见集合快照、取消与工具配对；本轮不新增并发工具执行|
|[Codex exec_policy](https://github.com/openai/codex/blob/main/codex-rs/core/src/exec_policy.rs)|显式区分禁止、需审批、配置允许|配置仅选择能力，单次命令确认仍独立；不迁移其命令策略语言|
|[DeepSeek ToolsService](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/src/index.ts)|注册与 dispatch 共用工具权限视图，最终 guard 可拒绝|permitted 同时用于 Schema 与 execute；MCP Catalog 激活不能扩大权限|
|[DeepSeek agent-loop](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/src/agent.ts)|步骤绑定的 resolved tool set|复用 AgentLoop 的请求级可见工具快照；不建立第二个循环|
|[Tools 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/tools.md)、[Pipeline](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-execution-pipeline.md)|执行前 guard、结构化结果、观察不等于授权|ToolResult 返回权限拒绝/未执行标识；现有命令/MCP审批与执行结果继续负责各自域|

DeepSeek 默认分支实际是 master；最初尝试 main 的四个原始文件 URL 返回 404，改用 master 后已读取，不能据初次 404 声称仓库缺失。

实现保持 Python：一个小型能力分类模块、Registry 执行门、一个 turn-local 合同模块。未迁移 Cordis、未引入 TypeScript、未建立插件授权框架或常驻 Judge。Task Contract 是本任务新增的保守证据视图，不声称上游实现了相同合同模型。
