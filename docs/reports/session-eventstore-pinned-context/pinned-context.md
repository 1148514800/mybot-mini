# Pinned Context v1

Pin是用户确认的跨轮任务参考，不是系统规则或权限，也不是自动长期记忆。分类：current_goal、user_constraint、confirmed_decision、open_question、pending_work。没有模型Pin Tool，不调用LLM提取，没有Contract→Pin自动写入。

每条包含pin_id、category、content、source_message_id、source_span、created_at、revision、status、superseded_by；source必须同session真实user.message的精确子串。索引按Python Unicode codepoint（不是UTF8字节或JS UTF16），Web做对应转换。脱敏后消息是可固定的实际来源，不能引用模型回复、别的session或虚构id。

Web点击用户消息“固定此消息片段”，在弹窗核对原文片段、类别，必要时选择替换旧Pin，点确认；折叠面板可查看来源、当前/撤销/替换状态和预算包含情况。撤销单独确认。CLI：

```text
/history
/pin confirm <message_id> <start> <end> user_constraint
/pins
/repin confirm <old_pin_id> <old_revision> <new_message_id> <start> <end> user_constraint
/unpin confirm <pin_id> <revision>
```

仅宿主用户接口能执行；Web消息输入拒绝CLI管理命令，使用对应按钮。模型没有创建/废除Pin能力。替换在同一事务新增新Pin、supersede旧Pin；expected_revision防止过期修改。revision是会话内**生命周期状态修订号**，不是语义版本；替换时新项先add、旧项后supersede，因此旧项状态修订号可能更大，不能按号推断哪条有效。有效性以status和superseded_by为准，源事件保留历史。

每条最多512字符；最多12条active/4096 UTF8字节；每session最多100条Pin历史（含撤销）。达到历史上限需显式新会话，不自动清审计。多个同类别active标needs_review，参考提示要求有疑义询问，不声称语义冲突已解决；v1不做自动语义冲突推理。

示例：固定“这个项目不允许使用第三方依赖。”；8轮长消息后仍进入实际请求。用户新消息“现在可以使用numpy，但其他第三方包仍不允许。”显式替换后，仅新Pin有效，旧项superseded可审计。撤销后active集合为空。

为避免撤销文本通过近期历史或摘要再次进入模型，构建请求前省略**包含撤销/替换Pin精确文本的整个历史协议轮次**，保留原DB和显示历史，不伪造/拼接tool result。统计pin_history_turns_removed和history_information_incomplete。保守过滤可能同时丢弃该轮无关信息，且不能识别所有语义改写；当前用户明确重新输入的文字仍是当前请求，不自动删除。不是模型遗忘证明或训练数据删除。
