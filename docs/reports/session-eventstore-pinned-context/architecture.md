# SessionEventStore v1 架构

本专题从 `2b8b2aa29a7adab5909730e85dc678ad60eb2a69` 开发；只增加会话基础设施，不引入 ORM、服务、插件框架或多 Agent。生产入口仍使用原 AgentLoop；模型、Controller、Patch、命令和审批权限没有新增能力。

## 三种独立数据

- **事实**：SQLite events 追加事件，事务内维护 sessions/messages/turns/tools/pins 索引投影。删除会话是显式的数据删除例外。
- **显示**：ConversationProjection 查询最近64条消息，可按 sequence 翻页（每页最多100）；Web 会话列表最多20。事件时间线只在当前进程保留128条，重启不恢复敏感工具卡片。
- **模型输入**：Session 是近期完整轮次缓存。恢复只投影已结束的安全聊天文本，最多100轮、默认6轮；不构造旧 tool result。Pins 是独立的当前参考集合。TaskStatusProjection 读取终态或中断状态，不恢复运行对象。

## 写入与调用关系

`config.storage_backend → history.open_store(channel + workspace hash) → SessionHistory`。CLI AgentLoop 自己拥有 history；Web ChatRuntime 先提交 user.message + turn.started，再将同一 history 传给 AgentLoop，避免双写。Registry 在权限检查后、工具实际 dispatch 前调用 history.begin，执行结束后调用 complete；事件只有名称/状态/副作用分类。模型请求前后记录 model 生命周期。ContextManager 生成请求副本；压缩事件只记计数/模式。

每次 append_many 先校验 schema/脱敏，再 BEGIN IMMEDIATE；生成 session 内连续 sequence、写事实、更新投影、校验配额，全部成功才 COMMIT。重试相同 event_id 与 canonical SHA256 则返回原 sequence；内容不同拒绝。ID 只由宿主 UUID 创建，模型工具没有追加事件的接口。

Web 在 MCP、client、Git capsule 清理完成后保存最终助手消息与状态，随后释放原 WorkspaceLease。取消、写入失败或清理不确定时不宣称永久完成。重启检查死进程的 pending/running，记录 interrupted 或 execution_uncertain。不会调度重放。

## 一致性与性能

SQLite 是持久化配置下的事实来源。UI 发送失败不撤销已提交事实；写入失败返回通用 storage_failed，禁止继续执行。空闲 GET 同步外部进程的新 sequence、删除和 context 边界；新 turn 清空旧 report/contract/approval，不接管活进程任务。SSE 只提供当前活动提示，断线/刷新使用受保护状态接口重新读事实。两个进程的追加由 SQLite 串行事务保护，工作区副作用仍由原 WorkspaceLease 保护。

每次操作关闭 SQLite 连接；不持有事务等待 LLM、子进程或人工审批。messages(session,sequence)、messages(turn,sequence)、turns(session,sequence)、pins(session,status,revision) 提供有界读取；每次请求不扫描完整 event log。完整性审查只在打开现有库时执行，有总容量边界。Pin最多12项，每次预算试排最多12次，无模型调用。性能结果见 offline-validation.json。

## 参考与取舍

阅读了 [Codex rollout 入口](https://github.com/openai/codex/blob/main/codex-rs/core/src/rollout.rs)、[rollout recorder](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/recorder.rs)、[session](https://github.com/openai/codex/tree/main/codex-rs/core/src/session)、[compact](https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs)、[app-server](https://github.com/openai/codex/tree/main/codex-rs/app-server)，以及 DeepSeek Harness 的 [session](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/session/src/index.ts)、[agent loop](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/src/agent.ts)、[session README](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/session/README.md)、[architecture](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md)。

借鉴持久事实与客户端/模型投影分离、明确 turn 生命周期和压缩边界；实现使用当前 Python 抽象和 stdlib SQLite，没有迁移 Cordis。上游路径会变化；本地合同与测试才是本实现的保证。
