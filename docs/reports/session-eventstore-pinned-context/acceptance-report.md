# SessionEventStore & Pinned Context 验收

**OFFLINE PASS**。基线2b8b2aa29a7adab5909730e85dc678ad60eb2a69；独立分支codex/session-eventstore-pinned-context。Implementation SHA：`713c3d28ac5ee0d9e27b9a9a6a740c74d7747963`。本报告由后续Acceptance提交交付，最终两次SHA与远程HEAD在交付消息核对。不合main、不改Phase Tag或ZIP，不进入下一Phase。

## 实现与问题回答

| 问题 | 实际保证 |
|---|---|
| 1 Web能跨重启恢复聊天吗？ | 显式event_sqlite支持标题、ID、消息、多个会话和安全状态；默认memory不持久化。浏览器A真实重启验证。 |
| 2 旧CLI JSON还能用吗？ | 能。省略backend且persist=true沿用旧SessionStore；无自动迁移/覆盖/双写；Web不读取旧JSON。 |
| 3 六轮以外早期信息会永久丢失吗？ | SQLite事实不随deque淘汰，可分页查看；不自动全量进入模型。自由文本会脱敏/按24,000 ASCII JSON字节保守截断并标记；全库配额到限拒绝，不自动删除。旧JSON维持原近期快照语义。 |
| 4 Event Log确定性和版本检查？ | v1严格payload、宿主UUID、每session连续sequence、事务事实+投影、幂等同ID重试/冲突拒绝；只读校验版本/完整性/规范hash/消息投影。 |
| 5 中断工具会自动执行吗？ | 不会。无重放调度，未完成标interrupted或execution_uncertain；有未知副作用阻止同工作区新任务，人工检查后显式复核。 |
| 6 会恢复旧审批权限吗？ | 不会。没有持久Receipt/nonce/Approval对象；不恢复旧Controller、Contract、Plan或verified。 |
| 7 Pin只由用户确认吗？ | 是。宿主CLI显式confirm，Web确认弹窗；同会话真实user.message精确跨度；没有模型Pin Tool或自动提取。 |
| 8 撤销后不再进入模型吗？ | 有效Pin中移除，并保守省略含该精确文本的完整历史轮次，避免摘要重引；原事实保留。语义改写和当前用户重新输入不是强制遗忘保证。 |
| 9 保留来源和版本吗？ | 保留message_id/codepoint span、创建时间、生命周期修订、revoked/superseded及superseded_by。替换事务原子、过期revision拒绝。 |
| 10 Pin进Token预算吗？ | 是。真实request副本含工具Schema、system/current、输出预留和配置窗口；最多12 active/4096 UTF8字节，逐项报告包含/省略；user参考角色。 |
| 11 CLI/Web共用且隔离吗？ | 共用stdlib SQLite/Memory引擎，channel+workspace hash命名空间隔离；只共享工作区安全阻止布尔，不共享私聊。 |
| 12 DB是否明文，如何限制？ | 明文。workspace外，0700目录/0600文件、UID/普通文件/单链接/inode/symlink/sidecar检查。建议APFS用户目录，不能保证ExFAT私有权限则拒绝。 |
| 13 删除实际保证？ | 用户确认后外键级联真实删除对应DB行，secure_delete；接口404且重开无记录。清上下文只是边界事件。日志/备份/SSD/快照可能残留，不保证物理擦除。 |
| 14 新的模型请求？ | 事件/投影/Pin增加0请求。原显式可选语义摘要和Failover仍受旧预算约束。本轮所有真实模型/摘要/付费Judge为0。 |
| 15 真实成功率还需Live吗？ | 需要独立明确授权和新的评测组；本次合成通过只证明机制，没有声称语义质量、真实任务成功率或费用改善。 |

默认17类事件；全DB最多50,000事件、64MiB主文件、单payload65,536 ASCII JSON字节，可配置硬界见[event合同](event-schema.md)。每次操作关闭连接，不持锁等待模型/审批/工具；近期历史和Pin有索引。SQLite原生hot journal回滚与任务恢复分离：事务内真实崩溃测试确认已提交聊天保留；陌生数据库及journal拒绝改写。SQLite与外部文件/命令不构成原子事务。

Pin参考优先于可裁剪旧历史；不会越过真实预算。语义摘要仍严格校验来源，失败不删Pin，不自动生成Pin。TaskContract仍只属于当前Coding任务。详见[架构](architecture.md)、[恢复](crash-recovery.md)、[Pin](pinned-context.md)、[投影与预算](context-projection.md)。

## 验证

- 新增5专项91项：Store22、Recovery18、WebPersistence24、Pinned17、Projection10，已加入check_phase。
- 最终权威check_phase：49组1539项，全部通过、0 skip，前后Python源码hash一致；独立离线补充79项通过。去重总数**1618 = 原1527 + 新91**，单独重跑不重复累计。
- 25个单独suite全部通过，含Web53、Session12、旧持久化16、Context18、Compaction22、ToolAuthority20、TaskContract22、RequirementEvidence16、Receipt53、CodingReliability42、ProviderFailover17、CodingFailover50、Command62及新增专项/独立补充。是离线机制检查，未重跑旧Live Attempt。
- compileall、app.js/markdown.js语法、git diff --check通过。代码及修改内容已检查；源码冻结前的开发运行不计入最终PASS。
- 真实子进程边界：任务未开始、user已写、模型等待、只读/副作用工具未返回、原生Preview、Commit完成、文件publish与事件之间、原生命令运行、原生unittest完成但回复未写；无重放/旧授权/虚假成功。另有DB事务内崩溃/native hot rollback、跨进程并发、清理失败、存储失败先于dispatch、MCP敏感参数/输出不落盘。
- 真实浏览器A–E全部通过；跨8轮及历史裁剪，撤销与替换后检查实际模型request有效Pin集合；SIGKILL真实合成命令server后恢复不确定，调用计数14→14；删除后刷新消失。见[浏览器记录与截图](browser-acceptance.md)。合成DB验收结束89事件、2会话、12 completed/1 execution_uncertain、Pin active/revoked/superseded各1；测试库不提交。
- APFS抽样10/100/500轮最近6轮+active Pin读取约0.4ms中位，完整启动校验单独计时；非并发SLA保证。精确结果、命令、日志SHA在[offline-validation.json](offline-validation.json)。

## 审计与限制

737个既有保护资产、52份原专项测试、14个核心安全/预算/旧存储文件与基线逐字节相同；无密钥、真实配置、DB/Session、缓存、AppleDouble、大型临时数据进入交付。原main及两处用户改动保留。详见[安全审计](security-audit.md)。

主要限制：本地明文、同UID攻击者与未知格式秘密、物理删除残留；外部副作用不具备跨DB原子性；PID重用保守阻止；恢复聊天不是完整请求回放；Pin限额/预算省略、撤销整轮省略及语义改写边界。真实模型长期质量未测。详见[剩余风险](remaining-risks.md)与[下一阶段](next-stage-readiness.md)。
