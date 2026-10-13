# Phase 04：Agent Planning

archive-ready: true

## 1. 学习目标与 Planning 存在的原因

多步骤任务需要公开的执行顺序与进度，避免模型遗漏步骤或只凭文字宣称成功。本阶段学习可选规划、结构化状态、工具证据和任务生命周期。计划是公开操作安排，不是模型隐藏推理。实现不增加分类 API、框架、数据库、长期记忆或多 Agent。

## 2. Agent 核心概念：DIRECT 与 PLANNED

DIRECT 继续使用原有 ReAct：普通问候直接回答，单步请求直接调用文件工具。PLANNED 由同一个模型响应通过 Function Calling 调用 create_plan 进入；计划仍由原有循环执行。没有独立 Planner 请求，也不用关键词匹配决定模式。

每次模型请求都能看到文件与规划工具的 Schema。系统提示要求简单任务不创建计划，复杂多步任务才创建。是否规划由模型选择，模拟测试验证两条路径和请求次数，不保证每个真实模型总能准确判断任务复杂度。

## 3. 完整架构及执行流程

```text
main → app → AgentLoop（Session + Plan + 现有 ToolRegistry）
每轮输入 → Plan.reset(user_input) → System + 历史 + 当前 User → LLM
 DIRECT：回答或 read_file/write_file/list_files → 原有 ReAct
 PLANNED：create_plan → update_plan(in_progress)
          → 文件工具 → 实际 ToolResult → Plan.observe
          → update_plan(completed/failed) → 下一步 → 最终回答
退出当前任务：Plan.close → 全部 completed 时正常回答
                         → 否则生成未完成报告
```

所有规划请求保留 assistant.tool_calls，规划结果保留 role=tool、tool_call_id；仍经 ToolRegistry 分发。默认文件注册表保留三个文件工具，AgentLoop 构造时额外注册两个绑定当前 Plan 的 PlanningTool。app.py 的用户修改未改动、未提交。

## 4. 核心文件与职责

| 文件 | 职责 |
| --- | --- |
| mybot/agent/planning.py | Step、Plan、PlanningTool，类型和转换校验、工具证据与展示 |
| mybot/agent/loop.py | 当前任务生命周期、规划工具注册、执行门控、实际结果观察、收尾 |
| mybot/agent/context.py | DIRECT/PLANNED 与顺序更新的模型指令 |
| mybot/agent/session.py | 原有完整用户轮次历史，默认 6 轮 |
| mybot/config.py | 原有模型、debug 与 session.max_turns 配置 |
| mybot/tools/base.py、registry.py | 复用 Tool、ToolResult、统一工具协议 |
| mybot/tools/file.py、list_files.py | 文件权限和工具执行，未修改 |
| scripts/check_planning.py | 12 项模拟模型规划测试 |
| scripts/check_phase.py | Phase 01–04 统一回归与归档入口 |
| scripts/save_phase.sh、restore_phase.sh | 原有独立源码归档与还原 |

## 5. Plan 数据结构、状态与验证

Plan 保存 task（当前用户输入）、有序 steps 和 closed。Step 保存 description、status、verified 与 error。create 校验 2–6 个非空字符串；模型不能用 extra 参数覆盖状态，规划参数类型也在本地验证。一个用户任务只允许创建一次计划，不允许覆盖、重建或恢复上轮计划。

状态转换：

| 当前状态 | 可转换为 | 条件 |
| --- | --- | --- |
| pending | in_progress | 前面的所有步骤均 completed |
| in_progress | completed | 当前步骤有实际工具成功结果，且没有随后失败 |
| in_progress | failed | 实际工具失败、模型报告失败或任务中断 |
| completed / failed | 无 | 终态，不支持自动重试或重新规划 |

非法编号（包括布尔值、字符串编号）、目标状态、逆序开始、重复完成、pending 直接完成等都返回失败 ToolResult。pending 不能跳过。模型不能用规划工具自己的成功结果作为执行证据。

## 6. create_plan / update_plan 与调用关系

PlanningTool 按名称暴露两个标准工具：

```json
{"name":"create_plan","arguments":{"steps":["列出文件","写入总结"]}}
```

```json
{"name":"update_plan","arguments":{"step":1,"status":"in_progress"}}
```

以上是易读的参数示意；真实 function.arguments 仍是 JSON 字符串，协议不变。create_plan 创建待执行步骤并打印计划；update_plan 使用 1-based 编号更新合法状态并打印进度。两者复用 Tool.to_schema、ToolRegistry.execute 与 ToolResult，不建立第二个执行框架。

AgentLoop._execute 区分规划工具与实际操作。规划工具走原有解析/校验/注册表，不积累证据；实际工具在 PLANNED 下必须存在 in_progress 步骤且没有失败，否则返回错误，不执行。实际结果交给 Plan.observe：成功设置 verified；失败立即将该步骤标为 failed，记录 ToolResult.error，后续步骤不能执行。一次响应可返回多个调用，沿用原有顺序执行，每个 id 都得到结果。

Plan.close 冻结当前计划。若最终模型文本出现时仍有 pending/in_progress/failed，应用使用未完成报告替换该终止文本，明确未验证或失败原因。Plan.task 关联当前输入；下一条用户输入重新 reset，即使 Session 含旧计划消息，也不能接着更新旧状态。

## 7. 真实工具执行、进度展示及异常

```text
[PLAN] 创建任务计划
[1/2] pending  列出文件
[2/2] pending  写入总结
[STEP 1] in_progress
[TOOL] list_files
[STEP 1] completed
```

默认规划展示只输出步骤描述、状态与工具名，不额外输出工具参数、结果正文或隐藏推理。原 debug 日志仍由配置开关控制，沿用 content 字符数遮蔽；debug 不是通用凭证脱敏器，不要把秘密放在计划描述中。

真实成功 ToolResult 是最小证据，不能等同于证明整个步骤语义正确。应用不理解自然语言描述与工具操作是否完全一致，也不验证总结质量；这属于本阶段局限。一个步骤若完全是文本推理或总结、没有实际工具结果，会保留未验证状态并报告。需要可验证输出时，可让总结步骤使用 write_file 保存产物；这只证明写入成功，不证明内容质量。

工具失败自动标 failed，最终报告保留实际错误原因，不再执行后续操作。超时、异常、中断、ReAct 上限将活动步骤标 failed，未开始步骤保持 pending，计划关闭并报告未完成。超时/异常依照 Phase 03 丢弃当前轮历史，旧历史保留；上限时补齐所有已收到调用的结果，再保存结束报告。已执行文件副作用不回滚。

/clear 同时清空 Session 和 Plan。默认保留 6 个完整用户轮次，继续支持 session.max_turns 配置。文件路径边界和原有工具参数保持不变。

## 8. macOS + uv 安装、运行与测试

```bash
bash scripts/restore_phase.sh 4
cd ../mybot-mini-learning/phase-04
uv sync --frozen
cp config/config.example.json config/config.json
# 配置真实 API 凭证（不要提交）
uv run python mybot/main.py
```

Python 3.12+、macOS/zsh、uv。可以先输入“你好”，再输入“列出工作区文件，然后将目录概况写到 summary.txt”。观察是否分别采用 DIRECT 与 PLANNED。文件写入权限仍限定 workspace。

```bash
uv run python -m scripts.check_planning
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot
```

ExFAT 开发目录编译可用 `-x '/\._'` 排除 AppleDouble；实际归档验证在 APFS 临时目录完整编译。

## 9. 自动化案例与实际结果

12 项 Planning unittest 使用模拟 LLM、临时工作区，无真实 API Key，均通过：

| 案例 | 验证结果 |
| --- | --- |
| 简单问候 | DIRECT，1 次模型请求，无计划展示 |
| 单步 list_files | DIRECT，原有工具循环，无额外规划请求 |
| 两步计划完整执行 | 结构化计划、真实目录工具和写入、依次 completed，7 个规划/操作 id 全部配对 |
| 非法参数 | 数量、类型、空描述、额外字段、编号和状态被拒绝 |
| 非法转换 / 无证据完成 | 拒绝跳步、重复更新、规划结果冒充操作证据 |
| 文件工具失败 | failed，拒绝假 completed、拒绝后续写入，报告实际原因 |
| 同一步先成功后失败 | 终态 failed，先前成功不覆盖后续失败 |
| 纯文本步骤 | 无操作证据，仍未验证，不沿用模型“完成”文本 |
| 未开始步骤直接执行 | 返回失败，实际文件未产生 |
| 模型超时 | 关闭失败计划、明确未完成，旧 Session 保留 |
| 模型异常 | 关闭计划、打印未完成报告，不污染历史 |
| ReAct 上限与 clear | 未完成状态及消息配对正确，clear 同时清空历史/计划 |

Phase 01 文件/日志回归、Phase 02 工具专用测试、Phase 03 的 12 项 Session 测试均通过。快照独立安装、编译及统一回归通过。

真实模型手工验证未执行；模拟测试证明协议和本地状态控制，不代表线上规划质量已经验证。

## 10. 局限与 Phase 03 → Phase 04

本阶段新增任务内的可选结构化规划和两个工具，仍是同一个模型与同一 ReAct 循环。Session 提供跨用户输入上下文，Plan 提供当前任务的执行状态，二者生命周期不同。Phase 03 的会话配置、完整轮次、clear、权限和日志保留。

顺序单活动步骤，单任务仅一个计划；无复杂 Replan、Checkpoint、自动恢复、并发、持久化或事务回滚。未完成任务下次输入会创建新任务，不恢复旧计划。成功证据只到 ToolResult 层面，不是语义正确性证明。历史仍按轮次而非 token 限制。AgentLoop 应使用独立 ToolRegistry，不能并发共享一个计划。

所有旧 Phase Tag/ZIP 保持不变，原有 app.py 和 workspace/instructions/USER.md 用户修改未混入本阶段。
