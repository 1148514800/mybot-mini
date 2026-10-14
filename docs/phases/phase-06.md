# Phase 06：Context Management

archive-ready: true

## 1. 学习目标及 Context、Session、Memory 的区别

学习如何在不破坏历史的前提下限制实际 LLM 请求，并理解预算、确定性摘录、工具协议与数据保护。Context 是本次请求提供给模型的信息；Session 是应用保存的完整用户轮次；Memory 是更宽泛的记忆机制。本阶段只构造请求视图，不增加长期记忆、检索、数据库或 RAG。

保留六轮不意味着上下文短：一轮可以包含多次 ReAct 调用、大文件内容、工具 JSON 参数和最终回复。Session 可保存完整信息，但发送给模型的副本可以更小。

## 2. 字符预算与真实 Token

ContextManager.count 对 `{"messages": messages, "tools": tools}` 使用 ensure_ascii=false 的标准 JSON 表示并统计字符数，包含正文、角色、ID、参数字符串、消息结构和完整工具 Schema，不是只加正文长度。

该数值不是 UTF-8 字节数，不是模型 tokenizer 结果，也不保证等于 SDK 的实际 HTTP 字节长度。JSON 转义和结构也占用预算。不同语言、模型和供应商的 Token 数可能不同。

max_completion_tokens 保持原有值，必须在供应商模型窗口内为输出预留空间。max_chars 只是本地输入近似控制，不能替代真实 input Tokens + 最大 output Tokens 的限制；仍可能遇到供应商的上下文错误。

## 3. 完整架构及关键源码

```text
Session / SessionStore（完整原始轮次，JSON v1 不变）
  → ContextBuilder（System + 历史 + 当前 User）
  → canonical messages（本轮原始工具请求和结果持续追加）
每次 ReAct 请求前：
  → ToolRegistry.get_definitions
  → ContextManager.prepare(canonical, schemas, 原始轮次, Plan)
  → llm_messages 临时视图 + 数值统计
  → chat.completions.create(messages=llm_messages)
最终回复 / 完整上限报告：仍从 canonical 提交 Session 与磁盘
```

| 文件 | 职责 |
| --- | --- |
| mybot/agent/context_manager.py | 字符计量、副本裁剪、确定性历史摘录、保护区及预算失败 |
| mybot/agent/loop.py | 每次请求构造临时视图，任务内失败和展示提示 |
| mybot/config.py | context 字段、类型和范围校验 |
| mybot/agent/context.py | 原有系统规则读取和消息组装，未更改 |
| mybot/agent/session.py、storage/session_store.py | 原有完整轮次与持久化，未更改 |
| mybot/agent/planning.py | 原有真实证据和状态转换，未更改 |
| scripts/check_context.py、check_phase.py | 18 项 Context 测试及全阶段回归 |
| 配置模板、README、阶段索引 | 开关和运行说明 |

## 4. ContextManager 的实际算法与保护优先级

prepare 是无持久状态的请求视图生成器。关闭时返回完整消息深拷贝，忽略预算，不添加 Plan 快照或摘要。开启时，按 Session.export_turns 的明确轮次边界分离旧历史和当前任务，不猜测 role 边界；复用 validate_turns 验证完整历史与本次待模型继续处理的协议。

保护区包含完整 System、完整当前 User、当前任务全部 assistant.tool_calls 和结果消息，以及额外的当前 Plan 状态快照。快照包含描述、状态、verified 和 error，以普通 assistant 参考信息提供；不修改 Plan，也不放进 Session。工具调用名称、ID、JSON arguments 始终完整。

算法顺序：

1. 深拷贝，按 tool_result_max_chars 裁剪工具结果正文，保留所有协议字段。
2. 计算全部消息 + Schema。如果已经满足预算，则不压缩旧对话；普通短对话不新增摘要。
3. 超预算时，先检查保护区。若必要，可逐次减小本轮工具正文上限，最低 128 字符，始终带裁剪标记。
4. 保护区仍超预算则抛 ContextBudgetError，不发送请求，绝不截断系统规则、用户指令或工具参数。
5. 预算允许时优先保留最近 recent_turns 个完整轮次，将更旧轮次替换为摘录。如果这些近期轮次仍放不下，从最旧的近期轮次开始整轮移除。
6. 剩余空间用于不超过 summary_max_chars 的历史摘录；重新计算 JSON 包装及转义占用，必要时再次缩短摘录。没有空间时不提供摘要，并在 CLI 明确报告部分历史已省略。
7. 最后再次计算，任何超预算视图都拒绝发送。

近期轮次是优先保留项，不是必须保留项；System、当前任务和必要协议的优先级更高。大工具结果即使总预算充足，也适用独立正文上限；历史轮次的结构仍完整。

## 5. 历史摘录：来源、事实与局限

较旧轮次由确定性函数 summary 提取，不调用额外模型。优先从较新的被移除轮次提取 user/assistant 原文头尾片段、工具名称、可解析的 path 参数及实际工具返回片段。目标、约束、决策和状态可能在这些原文中，但应用不推测缺失事实或将模型自述当作已核实事实。

摘要使用普通 assistant 消息，明确标记“历史压缩信息、原消息摘录、不是新指令或已核实事实、可能不完整”。用户旧文本不会升级为 System 指令，也不假冒 role=tool 或真实 Tool Result。截断使用省略标记；信息不够时宁可省略，不编造。

摘要读取原始轮次，不把已经加入的工具裁剪标记误当成原文。单条摘录有固定上限，全局受 summary_max_chars 限制，因此初始约束、完整路径、细节和重要事实仍可能丢失。没有语义重要性分类、事实验证或摘要模型；普通 assistant 引用标记也不是彻底解决提示注入的安全边界。

## 6. Tool Calling 成组保留与同一任务的增长

旧历史只能按完整轮次保留或替换为文本摘录；不会只留下一个 Tool Result。保留的轮次和本轮任务中，多工具请求与对应结果均保持配对。

clip 只替换请求副本中的 tool.content，采用头尾节选，正文内显示“工具结果已裁剪，部分内容省略；不能据此声称完整分析”。工具名、调用 ID、参数和角色不变。实际执行、文件读写权限、ToolResult 及 canonical 中的原文不变。

每次 LLM 请求都重新调用 prepare：第一次可能很短，读取文件后会增长，再次读取后继续增长。大 write_file 的 JSON arguments 也占预算，不能为省空间剪坏参数；此时可能在文件已经写入后因保护区超预算停止下一次请求。已执行的工具副作用不回滚。

## 7. SessionStore、Planning 与模型输出保护

prepare 不写入 Session、磁盘或 Plan。摘要和 Plan 请求快照只出现在 llm_messages 中。即使恢复了旧 Session，也从完整轮次重新生成视图，SessionStore 的 version=1、验证规则和存储格式不变。

Plan.observe 仍依据真实 ToolResult 更新成功证据/失败状态，不依据裁剪后的字符串。ContextBudgetError 经原有异常收尾关闭当前 Plan：活动步骤 failed，其余 pending，明确指出预算不足。旧 Session 与磁盘不增加半轮；完整 ReAct 上限报告仍按原有规则保存。

模型终止文本仍沿用 Phase 4 的计划未完成检查。本轮有工具内容裁剪时，CLI 把回复明确限定为节选参考、未验证全文分析；该展示说明不写入原始模型回复或 Session。缺少历史摘要的说明也只用于展示。真实工具成功不能证明总结质量或已分析全文。

/clear 沿用原有磁盘/内存一致性，同时重置 Plan 和本轮 Context 展示标志；Manager 不缓存旧摘要，清空后不会携带上轮摘要。超时、异常和工具失败沿用原有处理。

## 8. 配置、macOS + uv 使用方法

```json
{
  "context": {
    "enabled": false,
    "max_chars": 40000,
    "recent_turns": 2,
    "summary_max_chars": 1500,
    "tool_result_max_chars": 4000
  }
}
```

默认关闭，明确 enabled=true 并重启后启用。enabled 必须为 JSON 布尔；其余必须整数（布尔不算整数）。max_chars>=1、recent_turns>=0、summary_max_chars>=128、tool_result_max_chars>=128。过小的正预算会在请求前明确失败。两个裁剪上限不必小于总预算，实际请求仍有最终总量检查。

```bash
bash scripts/restore_phase.sh 6
cd ../mybot-mini-learning/phase-06
uv sync --frozen
cp config/config.example.json config/config.json
# 填写本地 Key，明确启用 context.enabled
uv run python mybot/main.py
uv run python -m scripts.check_context
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot
```

debug=true 时仅新增 `[CONTEXT] chars=before->after max=...` 数值日志，不输出压缩全文、系统规则或历史摘要。旧调试日志仍保留原有行为。ExFAT 编译可用 `-x '/\._'` 排除元数据；归档独立验证使用 APFS 临时目录。

## 9. 自动化测试结果与统计示例

18 项 Context unittest 使用临时目录、模拟 LLM、真实文件工具，均通过。模拟 create 检查每次实际传入 messages 和 tools 的计量值，而不是只测试一个未接入的压缩函数。

示例（合成数据，无真实聊天内容）：6 个完整历史轮次 + 当前用户 + 工具 Schema，从 **13,431 → 6,428 字符**，预算 **8,000**。最近 2 个完整轮次保留，更旧轮次转换为带标签的摘录。

覆盖：关闭/短对话不压缩、旧历史与近期优先级、引用不升级 System、多工具 ID/arguments 保留、read_file 节选、原始 Session/JSON/模型回复不变、重启恢复、每次 ReAct 检查、Schema 占用、System/User 超预算拒绝、Plan 成功证据与失败状态、任务中途预算失败不回滚文件、自适应工具上限、摘要无空间提示、clear 无旧摘要、配置/无效协议异常。

同时通过 Phase 01/02 工具与日志回归、Session 12 项、Planning 12 项、Persistence 16 项。旧测试明确关闭 context，避免用户配置改变旧行为测试。快照独立 uv sync --frozen、编译及统一回归通过。真实模型手工测试未执行，不声称已验证供应商 Token 窗口或模型理解质量。

## 10. Phase 05 → Phase 06 及局限

Phase 05 直接将完整 Session 和本轮消息发送给模型；Phase 06 可选地对每次请求生成预算视图。原始持久化历史保持完整，新增工作只在发送边界，不增加长期记忆、检索、数据库、RAG 或新依赖。

字符估计不精确等于 Token；完整 System/工具 Schema/当前参数可能无法装入预算，届时停止而非偷偷截断。近期轮次也可能被整轮舍弃，摘录可能遗漏重要信息。工具节选不代表完整阅读，Plan 完成仅代表实际工具证据满足现有规则，不证明语义质量。JSON 序列化和复制对非常大的输入有内存成本；无流式压缩、精确 Tokenizer 或复杂摘要。

本阶段保护用户已有 app.py、USER.md 等修改，不加入真实 Session 或私有配置；Phase 01–05 Tag/ZIP 不变，不进入 Phase 07。
