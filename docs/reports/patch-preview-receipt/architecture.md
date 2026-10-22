# Preview Receipt 协议与安全边界

本功能只在 `coding.preview_receipt=true` 时启用；默认 false，旧 Patch Schema、Prompt 和 CLI 调用方式继续可用。配置还必须显式启用 coding，并设置 patch_mode 为 preview 或 write。未来 Harness 通过 `GatewayConfig(coding_preview_receipt=True, coding_enabled=True, coding_patch_mode='write', ...)` 启用；`configuration()` 保留该字段，single 和 failover 共用的 registry 接收它。没有新 AgentLoop、子类或发布执行器。

```mermaid
flowchart LR
    A[模型显式 Preview changes] --> B[原生 preflight / recheck]
    B --> C[单份内存 Receipt 快照]
    C --> D[模型显式 Commit token]
    D --> E[消费 token / 作用域与时限校验]
    E --> F[全部文件重新 preflight / 版本比对]
    F --> G[原 Journal / stage / recheck / publish]
    G --> H[Revision 增加一次]
    H --> I[审批后的当前哈希 unittest / pytest]
```

成功 Preview 返回有界 Diff、`preview_receipt`、`can_commit` 和 `commit_arguments`。Commit 只需 `{"dry_run":false,"preview_receipt":"<本次返回的64字符令牌>"}`。Receipt 模式拒绝带 changes 的正式 Write；新版 changes Schema 描述只用于 Preview。Schema 是根 object，使用标准 JSON Schema oneOf/not 限定两种操作，未开启 OpenAI strict structured outputs。Draft202012Validator 已校验，原生工具定义可序列化；真实供应商对该 Schema 的接受情况仍需未来授权后的 Live 验证。

`PreviewReceipt` 是 frozen dataclass，关闭 repr。令牌由 secrets.token_hex(32) 生成，256 bit 随机值，不编码路径、源码或凭证；工具仅保存令牌 SHA256。最多一份有效快照及一份无正文的摘要墓碑。原 changes 已经过 256 KiB 输入预算校验，复制为不可变 JSON bytes；JSON 转义也有由输入上限推导的有限大小。快照保存全部规范路径、父目录 inode、完整 before/after SHA256、原文件 dev/inode/mode/uid/gid/nlink/mtime_ns/ctime_ns、已支持的属性、Diff 摘要、Workspace 路径及 inode、随机 turn scope、monotonic 创建/到期时间。scope 的脱敏哈希可进入诊断；scope 和 receipt 原值不进入报告。

每个 AgentLoop handle_message 新建 scope，在 finally 清除，覆盖完成、停止、取消和异常。/clear 也走 finally。显式 Receipt Write 在任何参数校验、权限或文件检查前先消费当前能力；失败也不能重放。新 Preview（包括失败的 Preview）撤销旧能力；非法 raw JSON 直接撤销且意图仍 unknown。过期能力在使用时拒绝并清除；turn 结束销毁全部快照。TTL 默认且最多 300 秒，不依赖墙钟；没有后台提交或恢复线程。过期但尚未访问的内存快照最多仍是一份，至下一次工具操作或 turn 结束释放，不是持久缓存。进程重启不恢复能力。

Commit 重新解码原快照，调用原 `_preflight`，对全部目标比对指纹和摘要；任何目标 stale、inode/版本/元数据或父目录身份变化都会在 stage 前拒绝全部文件。新增文件必须仍不存在。随后原 observer.before_publish 检查 Journal 归属、预算和基线；原 `_stage`、所有目标 `_recheck`、逐文件 `_publish`、published recheck、清理、observer.after_success 保持原调用顺序。stage 前及首次发布前额外检查 Receipt expiry、Workspace/scope 和 Controller deadline fence。原 Controller 的请求/批次/工具/Write/命令预算没有替代或绕过。正式 Write 失败一律 safe_to_retry=false；不确定状态保留 execution_uncertain。

Preview 不增加 revision；一次成功 applied Write 才增加一次，失败不增加。`file_revision_verified` 仅表示 Commit 的文件指纹核验，不表示测试通过。可信测试仍由原 Controller 与 Trace 的当前完整文件哈希、revision、非零测试计数、审批、Seatbelt、spawn/completed/exit code 等共同决定。python -c 不构成可信测试。工具 ID 的配对逻辑未改；跨模型 fallback 只请求响应，不执行 Patch，重复能力消费无法再次发布。

Receipt 原值只供当前模型请求中的显式确认。CodingTrace 仅复制白名单 bool/null/category 和 scope hash。结束时先将 Session 中 Patch 参数置空、对应结果替换为省略标记，并清理其余字符串中可能复制的 64 字符能力，再写 Session；保留 tool IDs 的一致映射和完整配对。没有 Preview 的磁盘补丁缓存；正式 Commit 仍使用原发布机制必需的临时 stage/backup 文件，随后校验并清理。原 Journal 的 before/after 仍按其原有有界内存规则保存。

继承边界：这是 POSIX 单文件原子发布与多文件 best-effort rollback，不是跨文件崩溃原子事务，也不是对恶意并发写者的 filesystem CAS。依赖文件系统实际报告的 stat 版本精度；不承诺超越原工具的 ABA/竞争防护。原权限/ACL/xattr、硬链接、敏感目录、路径逃逸、审批与 Seatbelt 政策均未放宽。
