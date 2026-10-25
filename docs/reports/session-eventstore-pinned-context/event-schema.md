# 事件合同 v1

数据库 application_id=0x4D594231，user_version=1；每条 schema_version=1。未知版本、损坏、不匹配 canonical 校验或序列/消息投影时停止并保留原库，不静默修复。没有隐式迁移。

共同字段：session_id/event_id 是宿主32位小写hex UUID；sequence 是同 session 从1起递增；timestamp 是宿主秒数（排序以 sequence 为准）；event_type、payload、source、privacy_class 均校验。source 只允许 host/user/model/user_confirmed/recovery；privacy_class 只允许 chat/metadata。表内 canonical 保存规范 JSON 的 SHA256，用于完整性和幂等，不作为密码学防篡改签名。

| 类型 | 必填 payload（不允许额外字段） |
|---|---|
| conversation.created | title |
| user.message / assistant.message | turn_id, content, truncated |
| turn.started | turn_id, owner_pid |
| turn.finished | turn_id, status |
| turn.interrupted | turn_id, status, reason |
| turn.reviewed | turn_id |
| tool.started | turn_id, tool_id, name, side_effect |
| tool.finished | turn_id, tool_id, success, effect |
| model.started | turn_id, purpose(agent/compaction) |
| model.finished / model.failed | turn_id, status / reason |
| context.compacted | turn_id, status, omitted_turns |
| context.cleared | 空对象 |
| pin.added | pin_id, category, content, source_message_id, start, end |
| pin.revoked | pin_id, expected_revision |
| pin.superseded | pin_id, new_pin_id, expected_revision |

精确类型、字符串范围和枚举见 event_schema.py 的 FIELDS/validate。user.message 必须 source=user；Pin和人工复核必须 user_confirmed；生命周期元数据只接受 host/recovery。source 是宿主路径声明，不能防同UID直接改库。

user.message 建立 pending turn；turn.started 绑定当前PID并检查安全边界；running才可 model/tool 生命周期。assistant.message + turn.finished 同一事务；仍有未结束工具时不能 finished。interrupted 不制造助手回复或工具成功。合法终态包含 completed、failed、cancelled、stopped、output_truncated、content_filtered、provider_error、response_unconfirmed、empty_reply、unknown_finish、interrupted、execution_uncertain 等原输出状态。工具effect=none/possible/changed；未知副作用不是成功。

同 event_id 同规范内容（含时间与来源）幂等返回原 sequence；不同内容拒绝。调用方重试需保留原 Event，重新生成 UUID 是另一件事实。跨namespace读取/重试拒绝。append_many 最多32条、全事务回滚，删除后该session不能重新读取。

默认全库最多50,000事件、64MiB主DB、每事件payload最多65,536 ASCII JSON字节。可配置硬界：事件1–100,000；DB1–256MiB；payload1,024–65,536字节。页数上限向下取整；达到配额停止写入，不自动删旧历史。临时rollback journal在私有目录内，磁盘需求可能超过主DB上限。聊天正文保守限制24,000 ASCII JSON字节，脱敏/截断均记录 truncated。
