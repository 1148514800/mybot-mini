# Phase 09：Agent Evaluation 2.0

archive-ready: true

## 1. 学习目标：任务成功与过程质量分开

Phase 8 的 task_success 同时包含产物正确、无工具错误和加载指定技能。真实运行暴露了问题：摘要和审查已经正确完成，却因没有调用 Skill 被判失败；计划调用出错后恢复成功，也被当作没有完成目标。

本阶段只改评测系统，不增加 Agent 能力。学习目标是用独立指标描述结果、过程、指令和效率，不强制 Auto 使用 Skill，不把小样本、固定模拟脚本或 Guided 提示差异当作技能收益证据。

## 2. 五类指标和 JSON v2

| 指标 | 判定依据 |
| --- | --- |
| task_success | 正常结束、实际源文件读取、真实产物/事实/缺陷检查通过；可恢复的工具错误不直接扣分 |
| process_clean | 无非预期工具失败、无运行错误/超时/上限，已建 Plan 完整结束 |
| instruction_followed | 用户明确要求的 Plan 或 Skill 已遵守；未提出技能要求时不要求使用 |
| skill_usage | 真实加载名称/次数、参考读取、相关请求和用量观察；是记录而非必选步骤 |
| strict_pass | task_success AND process_clean AND instruction_followed |

例：一次 update_plan 失败后纠正，结果文件正确且 Plan 完成，task_success=true、process_clean=false、instruction_followed=true、strict_pass=false。没有用 Skill 但正确完成 Auto 任务，四个布尔指标都可以为 true。

重复读取统计 duplicate_reads，不自动导致失败；复核文件可能合理。Plan 未完成主要影响过程；用户明确要求计划时还影响 instruction_followed。产物正确不能掩盖超时或没有正常结束。

JSON version=2 保存 task_checks、process_checks、instruction_checks 和带分类前缀的 grading_reasons，不再把通过率混为一谈。保留 task_success、checks、skills_enabled 等字段便于 Python 调用迁移，但旧报告 v1 的同名 task_success 语义不同，不能直接比较。

## 3. Off / Auto / Guided 的实验目的

Off 关闭技能，作为基准。Auto 开启元数据目录与技能工具，让模型自行判断是否需要加载；普通任务和复杂任务均不强制使用。

Guided 只用于有关联 expected_skill 的任务，在原任务末尾追加“请先读取相关 Skill，再按说明完成”。Trace 验证真实成功加载，并检查加载发生在文件操作之前。没有相关技能的案例跳过 Guided，因此各组分母可能不同。

Off/Auto 原提示完全一致，初始文件、模型/Provider、Context、ReAct、超时和输出限制一致；报告保存 prompt_sha256 可核对。Guided 的提示不同，单独标记 prompt_variant，不能把其差异全部归因于 Skill 内容。required_skill 只适用于原任务本身明确提出的技能要求，不因 expected_skill 元数据自动强制 Auto。

三个组每次都创建全新临时 Workspace、Session、ToolRegistry；不共享文件产物或历史。Persistence/debug 关闭，不读真实工作区 instructions，不改 System Prompt 或既有 Skill 描述。Session、ContextManager 与 Planning 仍使用原实现。

## 4. 为什么需要复杂 Benchmark

简单文件总结或单文件审查，模型通常直接调用通用文件工具即可。是否主动加载技能不是目标完成能力；若任务没有遗漏空间，也很难观察技能的收益。本阶段保留原十例并增加两例，总共12例。

complex-code-review 创建 storage.py、limits.py、service.py 和正确的 utils.py。三个模块存在路径边界、数量边界、异常返回和跨函数状态解释问题；正确函数作为干扰。用户提示只要求完整审查以及 file/function/evidence/trigger/impact/fix 的 JSON 输出格式，不泄露缺陷类型、数量或标签。

complex-document-summary 创建 requirements.md、meeting-notes.md、changelog.md、decisions.md。初始草案、未批准提议、取消事项和最终决定互相冲突，需要区分现行方案与过期信息并保存 project-summary.json。提示只提供输出键/格式，不给最新日期、负责人、预算或预期答案。

Fixture、人工标注和 Offline 响应脚本在 evals/cases.json 中版本管理。Live 模型只得到任务文本与隔离 Workspace，通过工具读合成来源；评测器不会把 expect、review_annotations 或 Offline 答案加入消息。两个新任务均可跑 Off/Auto/Guided，不能为了提升技能选择率修改任务结论或系统提示。

## 5. 客观质量评分与 Precision / Recall

grader.grade 要求指定源文件真实读取成功，再检查最终结果。复杂审查将回复解析为 JSON，要求每项六个字段非空；命中必须同时匹配文件、函数和多组具体代码/机制证据，不靠一个风险关键词通过。未知文件/函数、证据不足或把正确函数报成缺陷会计误报；未覆盖人工标注计漏报。

- true_positives：命中的不同真实缺陷数。
- false_positives：没有匹配标注的报告项数。
- false_negatives：标注缺陷中未命中的数。
- precision = TP / (TP + FP)，没有报告时为 null。
- recall = TP / (TP + FN)，没有可评分标注时为 null。

本样例有四项标注，三项命中加一项错误报告得到 precision=.75、recall=.75。重复报告同一缺陷不增加 TP。task_success 要求无漏报、无误报和格式正确。trigger/impact/fix 只是结构检查，其解释质量仍 manual_review_required=true；没有使用被测模型作为 Judge。

跨文档产物按 JSON 字段比较当前日期、语言、部署、负责人、预算、约束及过期方案。数组顺序不影响评分；遗漏、旧决定、错误值或新增无来源字段都会失败。读取四份来源是独立条件，不能只读最终决定而通过。严格英文值/格式能保证确定性，但合理改写可能被拒绝；人工仍应检查语义和来源关系。这不是对任意自然语言事实的完整验证。

## 6. Planning 诊断与效率追踪

trace.error_category 对照现有 PlanningTool 返回的固定错误精确映射：plan_missing、plan_invalid_step、plan_invalid_status、plan_step_order、plan_not_in_progress、plan_unverified、plan_recreation。未匹配归 other_tool_error；不推测参数，不保存错误全文，不修改 Phase 4 状态机。

TracedAgent 先调用原 _execute，再观察实际 ToolResult。planning_failure_categories / planning_tool_failures 统计控制工具失败，Plan 最终 status 继续记录。file_tools_before_plan 是计划创建前的文件工具次数；DIRECT 没有计划，所有文件工具都属于“尚未创建计划”，该计数本身不代表错误。

duplicate_reads 将当前临时工作区中的解析后路径归一化，内存中用哈希计数；./fact.txt 和 fact.txt 视为同文件。它统计重复尝试，包括失败尝试，不擅自判断必要性。报告只保存次数和白名单合成路径，其他完整路径不保存。观察路径异常也不能改变真实工具的执行结果。

Skill 记录成功加载、加载尝试、成功参考读取、工具响应批次、带技能 Tool Result 的后续请求数与字符数，以及这些请求的供应商 Token 用量。这些是实际观察，不是技能“净增成本”：同一请求也可能完成文件工作，无法从一次运行知道不加载技能时的反事实用量。因此 extra_llm_requests / extra_tokens 保留 null，不编造精确边际成本；可以对照不同组总请求/Token，但 Guided 提示差异与随机性需要单独考虑。

## 7. 代码职责与调用关系

```text
scripts/eval_agent.py：解析 --case-ids / --groups / --live / --analyze-report
  → runner.select_cases：未知/重复 ID 拒绝，按选择顺序限制数量
  → evaluate：分组与重复共享请求额度，Guided 无关案例跳过
  → task_prompt：仅 Guided 增加明确技能要求
  → 临时 Fixture + 原 AgentLoop 的 TracedAgent
  → TracedClient / Trace：真实请求与工具结果，安全分类与效率计数
  → grader.grade：独立的任务/过程/指令/质量检查
  → summarize：按组输出各指标、成本、审查质量
  → save_report：忽略目录中的唯一 JSON 报告
```

history.analyze_report 专门做只读历史分析。其他新增主要是 scripts/check_evaluation_v2.py 与复杂 Fixture；原 scripts/check_evaluation.py 的18项机制测试更新到新评分语义，check_phase.py 接入本阶段。没有新依赖，没有修改 AgentLoop/Planning/Skills 的实际协议。

OfflineClient 不再根据 expected_skill 自动插入 load_skill。Off/Auto 使用明确的普通脚本；Guided 的固定 guided_actions 在案例文件中单独标注为 skill-loading smoke test，报告 response_source=fixed_offline_script、offline_script_label。这只能证明评分/加载链路，不代表模型自主选择，不能解释为能力成绩。

## 8. 旧报告只读分析与证据边界

```bash
uv run python -m scripts.eval_agent --analyze-report runs/evals/live-20261014T150141-d6a742f5.json
```

默认只打印新口径汇总，不写原文件、不发请求；需要另存分析结果时可指定 --output runs/evals-analysis，独占创建新文件。--analyze-report 与 --live 不能同时使用。

v1 保存的 checks 能重新分离结果/过程/指令。没有原始回复或临时产物，因此不是重新执行完整 Grader，而是基于旧检查证据的重新解释；analysis_only=true、source_version=1 和 analysis_limits 明确标记。缺失字段为 unknown/null，不能从历史摘要推断新参数。

用户指定旧报告实际重算：Off task=6/6、clean=6/6、strict=6/6；Auto task=6/6、clean=5/6、strict=5/6。多步骤任务两次失败类别 unknown，重复读取1次，计划创建前文件工具2次。原报告 SHA-256 在分析前后相同。summary/code-review 未使用 Skill 不再导致任务失败。未知文件路径使历史重复读取数只能是下界，缺少请求归因的技能边际成本保持 null。

## 9. macOS + uv 使用与实际测试

```bash
uv sync --frozen
# 保留默认 Off/Auto，前10例
uv run python -m scripts.eval_agent
# 所有案例及三组（离线固定脚本）
uv run python -m scripts.eval_agent --max-cases 12 --groups off,auto,guided
# 选择复杂任务；multi-step 无相关技能，Guided 跳过
uv run python -m scripts.eval_agent --case-ids multi-step,complex-code-review,complex-document-summary --groups off,auto,guided
uv run python -m scripts.check_evaluation
uv run python -m scripts.check_evaluation_v2
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
uv run python -m compileall -q -x '/\._' mybot scripts
```

真实评测由用户显式运行，可能收费，本次开发未运行：

```bash
uv run python -m scripts.eval_agent --live --case-ids complex-code-review,complex-document-summary --groups off,auto,guided --max-requests 80 --timeout 60 --repeats 1
```

max-requests 是跨案例/三组/重复的全局上限，达到就停止请求并记录失败；timeout 是整例上限；SDK 重试仍关闭。输入/输出 Token 缺失为 null，total_tokens 仅在两者都已知时相加。报告继续脱敏，不含 API Key、原始错误、聊天/工具/技能全文；最终输出仅长度/哈希，runs 已忽略。

实际完整 Offline：Off12/12、Auto12/12，均25工具/37请求且没有模拟加载技能；Guided4/4，20工具/24请求，4次明确脚本加载。无关联的8例跳过 Guided。四项布尔指标都通过，Token=null；成绩只代表机制。18项原评测测试和15项新评测测试通过，覆盖错误恢复、未完成计划、迟加载/错误技能、联合证据误报漏报、过期/遗漏/无来源信息、真实Planning分类、重复读取、三组隔离、选择参数、答案不泄露、旧报告只读、限额/超时/脱敏。

Phase01/02、Session12、Planning12、Persistence16、Context18、Skills16 回归通过。归档安全检查及独立 ZIP 冻结安装/编译/统一回归使用 APFS 临时目录；不包括评测报告或用户数据。

## 10. 变化、限制与后续边界

Phase 8 的综合 task_success 拆为 v2 的结果、过程、指令和 strict；A/B 增为可选三组；新增复杂基准、安全诊断和只读历史分析。Off/Auto 不加载技能也可成功，Guided 明确使用要求独立评分。旧Tag/ZIP和旧报告不可变。

固定模板、双语证据片段和严格JSON只能评价本 Benchmark，不是通用语义裁判；真实合理改写可能产生误判。修复建议正确性、事实关系和其他未标注缺陷仍需人工。没有 LLM-as-Judge、统计显著性检验、自动成本报价、多轮记忆基准或产物留存；重复读取不自动判无效。

真实模型存在随机性；Guided 有额外提示，不能证明技能内容的单独因果收益。Token 归因只观察带技能的请求，精确净增成本未知。历史报告缺少错误参数/正文，unknown 不能补猜。新评分与旧评分不可直接比较，除非明确做只读重解释。

只运行离线开发测试，不改模型路由、系统提示或技能描述，不执行Shell工具、不新增Agent框架，不Push，不进入Phase10。app.py和USER.md用户修改保留；ExFAT ._* 尽量减少、归档排除，不承诺系统完全不生成。
