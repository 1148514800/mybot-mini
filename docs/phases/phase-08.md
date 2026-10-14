# Phase 08：Agent Evaluation

archive-ready: true

## 1. 学习目标：从“回复完成”到验证真实执行

Agent Evaluation 是用固定任务、初始数据和明确评分规则评价 Agent 行为的过程。本阶段学习 Benchmark、Fixture、Trace 和 Grader，并比较技能关闭/开启时的实际调用。没有新增 Agent 功能或第二套执行循环。

单元测试证明某个实现符合条件，但不能证明真实模型能自主选工具、读取文件并完成任务。模型具有随机性，还受到 Provider、模型版本、提示和预算影响。因此分开记录 Offline 与 Live，绝不把模拟响应的成绩当成真实模型能力。

## 2. 两种模式与费用边界

Offline 是默认模式：OfflineClient 按案例预设脚本返回 Function Calling 和最终文本，文件工具仍真实执行在临时工作区中。无需 Key、不构造真实 API Client、不访问模型服务。脚本知道预期答案与预期 Skill，用来验证框架机制，不用于测量自主发现能力。报告 mode=offline、ability_score=false、model=offline-script、provider=offline。

Live 只有显式 `--live` 才调用当前 GatewayConfig 的 Provider、Model、Key 和 base_url。CLI 在启动前提示可能产生费用；Key 和 SDK 错误正文都不打印或记录。SDK 自动重试被关闭，每次真实尝试都经过统一请求计数。开发、回归和归档只运行 Offline。

`--max-cases` 限制不同任务数，每个任务分别测试 A/B；`--repeats` 重复完整对照。`--max-requests` 是整个运行的模型请求总预算，包括所有案例、两组和重复，不是每个案例的额度。额度耗尽不再发起任何请求，后续案例标为 model_request_limit。`--timeout` 包括单个案例的完整 Agent 任务；既有模型请求超时也保留。超时取消当前请求、记录失败并清理临时目录。

## 3. Benchmark 与可复现 Fixture

`evals/cases.json` 使用 version=1，存放十个合成小任务。每例包含 ID、自然任务文本、初始文件、Offline 脚本和评分规则；expected_skill 不送给 Live 模型。加载时检查版本、唯一 ID、路径与生成文件大小。长文件用有限次数的重复文本生成。

| ID | 任务与客观检查 |
| --- | --- |
| greeting | 中文问候；不创建 Plan、不加载技能 |
| list-files | 真实 list_files 成功，回答两个初始文件名，DIRECT |
| read-fact | 实际读取 fact.txt，回答 ORION-42，DIRECT |
| multi-step | 列出/读取/写 result.txt，Plan 完成，产物含四项事实 |
| file-summary | 自然描述总结 notes.txt、保存 summary.txt；B 应选 file-summary |
| code-review | 读取人工标注的 review.py；识别 EMPTY_INPUT 与 DIV_ZERO，不报额外缺陷；B 应选 code-review |
| irrelevant | 回答 2+2；不创建 Plan、不加载 Skill |
| missing-file | 实际 read_file 失败，回复 NOT_FOUND，不宣称读取成功 |
| long-context | 读取长合成文本，实际下一请求有裁剪标记、保留首尾事实，不宣称全文分析 |
| write-content | write_file 成功，hello.txt 严格匹配指定内容与换行 |

技能选择案例没有要求调用 load_skill。Live 模型只能从目录元数据和任务需求发现技能；Offline 的预设加载仅做链路验证。代码审查样例和标签在版本管理中可追溯。语义解释质量、遗漏其他合理意见仍需要人工审查；没有 LLM-as-Judge。

## 4. 实际架构和核心文件

```text
scripts/eval_agent.py：CLI 参数与 Live 费用提示
  → runner.evaluate：检查限额，读 cases，逐次/逐例/A-B 运行
  → 临时 Workspace + 合成 Fixture + 全新 Session/ToolRegistry
  → 原 AgentLoop（TracedAgent 仅观察真实结果）
  → TracedClient → OfflineClient 或配置中的真实 Client
  → grader.grade：检查真实文件、事件、输出事实、Plan
  → JSON results → summarize → save_report → 终端汇总
```

- `mybot/evaluation/runner.py`：案例加载、合成文件、隔离执行、异常收尾、报告写入。
- `trace.py`：轻量 Client 包装与 AgentLoop 子类，记录实际事件而不改变执行结果。
- `grader.py`：确定性条件与分组汇总。
- `evals/cases.json`：任务、Fixture、脚本和规则。
- `scripts/check_evaluation.py`：18 项框架测试。
- `scripts/check_phase.py`：加入 Phase 8 离线回归；归档安全测试夹具包含 evals。

没有修改 AgentLoop、ToolRegistry、SkillRegistry、ContextManager 或正常应用 app.py 的执行语义，也没有引入新依赖。

## 5. Runner 的完整调用流程

`evaluate` 默认创建统一评测配置：Context 开启、max_chars=40000、工具结果上限1000、ReAct 上限16；其余模型、输出 Token、请求超时和历史参数沿用当前配置。该评测设置作用于隔离实例，不写入用户 config.json。A/B 使用完全相同设置，唯一区别为 skills_enabled。

每个案例、组和重复创建一个 TemporaryDirectory，写入相同 Fixture，创建新的 ToolRegistry 和 AgentLoop。强制 session_persist=false、debug=false；使用临时 Session 路径，不加载真实聊天历史，也不读取正常工作区 instructions。Skills 使用配置的可信技能目录，默认仓库示例。

`TracedClient.create` 在请求前检查全局额度，计数并记录实际请求字符数、消息数、裁剪标记；调用后记录响应长度、调用数和 usage。`TracedAgent._execute` 先调用原实现，再观察 ToolResult，包括参数错误、Planning 阻止和工具失败。`_finish_turn` 只记录正常结束/步数上限，其他行为交给原实现。

`asyncio.wait_for` 包住整个任务。异常、超时、ReAct 上限、上下文预算不足和技能初始化失败都有失败记录。Plan 原有收尾继续运行，未完成状态不能通过评分。之后评分并离开临时目录，全部文件和会话清理；已执行工具不会影响用户工作区。

## 6. 确定性 Grader 与成功含义

`grade` 同时要求没有运行错误、正常结束、所有已创建 Plan 步骤 completed。一般案例中任何失败 ToolResult 都导致失败；missing-file 特别允许预期 read_file 失败，但要求失败真实发生并准确报告。

文件检查读取实际产物，确认位于当前临时工作区、存在、大小受限，然后比较完整文本或必需事实。仅模型声称“写好了”没有文件、文件内容错误、读取错误源文件，都失败。Trace 只记录白名单中的合成文件路径，评分要求源文件读取成功。

普通输出使用预标注的必需/禁止文本，工具要求依据真实成功结果。code-review 从最终回复中提取 `DEFECT: LABEL`：命中、误报、漏报分别计数；既要求所有真实标签，又禁止额外标签。manual_review_required=true 表示解释质量仍需人工确认，即使客观标签部分通过。task_success 表示这组公开规则通过，不等于证明语义完美或通用能力。

Skills A 组没有技能工具，预期不加载技能；B 组在指定任务要求正确技能，其他任务禁止误选。成功读取技能不能替代文件产物，也不作为 Plan 执行证据。长文本案例从真实发出的请求元数据检查裁剪，不靠模型自称裁剪。

## 7. Trace、统计与隐私

保存的事件包括 llm_request/response/error 与 tool，含请求字符数、文本长度、调用名称、成功状态、合成文件白名单路径和耗时。未知调用名记作 `<unknown>`；失败正文不保存。没有完整消息、参数、文件内容、技能正文、Plan 描述、Key、base_url 或 SDK 原始错误。

最终输出默认仅保存长度和 SHA-256；评分在内存读取完整回复，报告保存条件结果、缺陷计数和失败代码。这样记录实际输出的标识而不持久化可能包含隐私的正文。需要人工审查语义时，应另行在受控环境做手工验证；本阶段不保存文件产物。

每例记录 task_success、tool_calls、tool_failures、llm_requests、skill_selected、expected_skill、planning_completed、Plan 状态、duration_seconds、input_tokens/output_tokens、error。DIRECT 的 planning_completed=null；没有 usage 或其中任何请求缺少字段时累计 Token 为 null，不猜测。失败请求也计入次数，部分使用量不足以报告完整 Token 总额。

JSON 还包含 UTC 时间、Git Commit、案例内容 SHA-256、模型/Provider、公共配置、重复编号与分组汇总。报告独占创建，不覆盖旧报告；`runs/` 已由 .gitignore 忽略。没有价格数据，因此不估算费用。耗时用 perf_counter 测量，数值每次不同；评分条件和汇总可从 results 重新计算。

## 8. Skills A/B 的解释

A/B 使用相同模型、Provider、任务、初始文件、Context 和 ReAct 限制，每组独立 Session/工具/目录。技能索引和技能工具 Schema 自然只出现在 B。每次重复单独保留结果，不复用 A 产生的文件和历史。

对比成功率、技能选择、工具次数/失败数、Token 与耗时。单次小样本不能证明 Skills 提升能力；应在固定配置下多次 Live 运行，检查各任务波动和失败原因。Offline 脚本会自动加载案例指定技能，因此其成功率和选择率只能证明记录与评分机制，绝不能据此宣称 B 更聪明。

## 9. macOS + uv 命令与实际验证

```bash
uv sync --frozen
uv run python -m scripts.eval_agent
uv run python -m scripts.eval_agent --max-cases 3 --max-requests 20 --timeout 10 --repeats 2
uv run python -m scripts.check_evaluation
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
uv run python -m compileall -q -x '/\._' mybot scripts
```

用户明确选择后才可自行运行（开发与归档未运行）：

```bash
uv run python -m scripts.eval_agent --live --max-cases 3 --max-requests 30 --timeout 30 --repeats 2
```

默认报告位置 runs/evals/，可用 --output 指定报告目录。max-cases=3 表示每次重复最多3个任务×2组。缺少 Key 是配置错误；API 调用异常是失败结果，不当作任务完成。报告中的 Live 标签仅表示显式模式，不保证所有任务都成功。

实际 Offline 十任务 A/B 各10/10通过：A 工具16次、模型请求26次；B 工具18次、模型请求28次，分别加载 file-summary/code-review；usage 均为 null。额外请求来自两项技能加载，不是性能优势。18 项框架自动化测试通过，覆盖默认无真实API、显式Live的模拟客户端、隔离、真实追踪、失败/缺产物/错误内容/错误源、技能误选、全局限额、超时/异常/初始化错误、usage、Plan/ReAct、真实裁剪、JSON重算/隐私及参数验证。

Phase 01/02、Session12、Planning12、Persistence16、Context18、Skills16 原有回归通过。归档安全检查、ZIP冻结安装/编译和统一离线回归在独立 APFS 临时目录执行。真实 Live 未运行，不能提供模型能力成绩。ExFAT AppleDouble 不进归档，用户 app.py/USER.md 修改保留。

## 10. Phase 7 → Phase 8 与局限

Phase 7 提供技能能力；Phase 8 新增观察、固定任务、隔离、确定性评分与 A/B，不增加 Agent 执行功能。复用一个 ReAct 循环，保留 Session、Planning、Context 和技能安全边界。

局限：十个合成任务覆盖有限；字面事实规则不能可靠验证语义关系，缺陷标签只能评价人工标注的风险，审查解释需要人工；没有 LLM Judge、价格估算、统计显著性检验或多轮会话 Benchmark。重复任务独立而非同一会话延续。临时目录路径不同可能影响真实模型输出，报告 Git Commit/案例哈希也不能锁住远程模型版本或消除随机性。没有完整正文 Trace 和产物留存，隐私优先会限制离线人工复盘。

Live 会使用用户管理的可信技能目录；比较时应冻结技能内容与配置，避免运行中修改。超时取消等待并清理工作区，不保证供应商停止计费。每个实际 API 尝试占预算；不自动重试。支持单进程串行评测，不支持分布式评测或任意Shell。历史Tag/ZIP不变，不进入Phase9，不自动Push。
