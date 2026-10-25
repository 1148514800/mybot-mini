# AI_HANDOFF

## 当前目标与状态

SessionEventStore v1 & Pinned Context v1 已完成实现、离线专项/全量、真实浏览器A–E和安全审计。独立分支codex/session-eventstore-pinned-context，基线2b8b2aa29a7adab5909730e85dc678ad60eb2a69；Implementation已提交713c3d28ac5ee0d9e27b9a9a6a740c74d7747963；本快照所属后续docs提交为Acceptance，按用户授权仅Push专题分支，远程HEAD与干净状态在最终交付核对。不合main、不创建Phase26、不改旧Tag/ZIP。

## 当前实现与决策

- 可选memory/legacy_json/event_sqlite，默认memory。旧CLI JSON未改、不自动迁移/双写；Web不读CLI JSON。channel+workspace hash隔离，共用事务引擎，仅共享安全屏障。
- stdlib SQLite v1，宿主UUID、连续sequence、canonical SHA幂等/冲突、原子事实+投影。默认50,000事件/64MiB/单payload64KiB；私有0700目录/0600文件、workspace外、UID/symlink/inode/sidecar检查。已有库校验，识别v1的hot journal只允许SQLite原生回滚，陌生/损坏库拒绝重建。
- Conversation/ModelContext/TaskStatus独立投影，近期有界与原事实分离。恢复安全聊天和真实终态，不重放模型/命令/Patch，不恢复Receipt/nonce/Contract/verified。未知副作用或清理失败持久化execution_uncertain，原WorkspaceLease不变，人工复核不证明成功。
- Pin仅宿主用户确认、真实user消息精确跨度；增/撤/替换保留来源与生命周期修订。最多12 active/4096 UTF8字节/100历史；user参考角色，计入实际上下文预算、逐项明确遗漏。撤销/替换前先整体省略含精确旧文本的历史轮次，不删审计，不伪造tool结果。摘要失败不改Pin，不增加固定模型请求。
- Web提交user后才执行，资源清理后保存终态，存储失败不宣称永久成功；空闲同步外部进程变更/删除/context边界。清上下文不等于删SQLite历史，确认删除才级联真实删行；不保证物理擦除。

## 验证与文件

新增5专项91项（22+18+24+17+10）；最终check_phase49组1539项+独立79=去重1618，全过、0 skip、前后源码hash一致。原1527保留，25个专项单独重跑通过，compileall/JS/diff检查通过。真实子进程覆盖任务/工具/Preview/Commit/命令/测试后回复前以及事务内崩溃；真实浏览器A–E通过、重启0自动调用。真实DeepSeek/GLM/语义摘要/付费Judge均0。

核心新增storage/event_schema/event_store/event_privacy/history/projections、agent/pinned_context；接入config/registry/loop/context_manager/app/Web与静态页；5专项及合成fixture加入check_phase。完整设计、验证和截图在docs/reports/session-eventstore-pinned-context/，README和docs/web-ui已更新。

737旧保护资产、52原check专项、14核心安全/预算/旧存储文件逐字节未变；无秘密/真实Session/DB/配置/AppleDouble提交。原main HEAD8c1a049904f9544fc5eaeb53c06f6712e43ea320及mybot/app.py、workspace/instructions/USER.md用户修改未动。

## 限制与下一步

SQLite不与外部副作用原子提交；同UID攻击者、明文/备份/SSD残留、PID重用仍有风险。恢复不是完整请求回放；Pin有预算省略与保守整轮省略，不能识别所有语义改写/冲突。真实长期任务质量仍需新授权Live；没有使用旧额度，不重跑旧Live、不改冻结资产。

实现与验收资料已齐全；交付时核对专题Push、远程HEAD与工作树，随后仅在用户新任务下继续。不要重复实现存储/Pin、自动迁移、自动LLM记忆或进入下一Phase。
