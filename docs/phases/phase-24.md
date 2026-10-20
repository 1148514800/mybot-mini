# Phase 24：Real-Model Coding Agent Evaluation — 真实模型接口与隐藏测试评测

版本说明：第1～14节保留初始`phase-24`归档时的验证事实。归档后Live结果及审批、Patch提示、命令超时、预览错误诊断、Planning预算指引、cwd和Patch提交契约见第15～20节，不能再将“尚未调用模型”的历史描述当作当前状态。现有Tag/ZIP仍是原快照，后续修复不覆盖它们。

## 1. 目标、数据来源与当前结论

本阶段建立安全、可重复、可审计的 Coding Benchmark，不新增 Coding Tool，不重写 AgentLoop，不实现 RSI、自动 Commit/Push 或模型 Reviewer。

Harness Evaluation 检验预算、工具、隔离、评分与记录是否可靠；Model Evaluation 则要求真实 Provider 自主调查和修改未知代码，再由独立评分器判断结果。固定 Reactive Client 只具有预先写好的策略，其成功不能代表模型编码能力。

**真实模型 Coding 能力尚未实测，当前完成的是安全、可重复、支持真实模型的 Benchmark 评测系统。** 本阶段没有执行付费 Live 请求，没有实际 API 请求费用；actual_tokens、estimated_cost、real_model_repair_rate 保持 null，不能将 null 当0或离线成功率。

任务是本项目新构造的12个标准库 Python 小项目，不是从用户业务仓库、外部网络或 SWE-bench 导入。每项有自然语言契约、实际缺陷、2个公开测试、4个独立隐藏测试和可信 Reference Fix。隐藏测试是运行时隔离，并不证明模型训练中从未见过类似问题；基准公开后也可能发生记忆污染。结果不能直接与 SWE-bench 对齐，不能外推生产项目能力。

## 2. 任务库与难度

| Case ID | 难度 / 生产模块数 | 用户契约与真实缺陷 | 公开 / 隐藏 |
| --- | --- | --- | --- |
| config-default-001 | Easy / 1 | False覆盖默认True，拒绝非bool；原实现用or吞掉False | 2 / 4 |
| cache-ttl-001 | Easy / 1 | 到期即失效、0立即失效、负TTL无效；原实现边界和参数有误 | 2 / 4 |
| pagination-001 | Easy / 1 | 正整数1起始页码、完整页面；原切片少一项 | 2 / 4 |
| serialization-001 | Easy / 1 | 只省略None；原字典筛选丢失False/0/空串 | 2 / 4 |
| csv-export-001 | Medium / 2 | 标准CSV引号、逗号/引号/换行；原实现直接join | 2 / 4 |
| timezone-day-001 | Medium / 2 | 转换UTC后取日期；原replace覆盖offset导致跨日错误 | 2 / 4 |
| file-recovery-001 | Medium / 2 | 类型/编码失败保持旧字节，安全替换与清理；原实现先截断 | 2 / 4 |
| cli-precedence-001 | Medium / 2 | CLI→配置→默认，保留0；原参数默认和or混淆未提供与显式值 | 2 / 4 |
| validation-chain-001 | Hard / 3 | 规范化→校验→返回规范化邮箱，跨模块顺序/契约错误 | 2 / 4 |
| cache-sync-001 | Hard / 3 | Store写入→精确失效→Cache读取；失效为空操作且传错key | 2 / 4 |
| parse-convert-001 | Hard / 3 | 首冒号分割、strip、整数转换、服务装配；多个模块漏转换 | 2 / 4 |
| error-retry-001 | Hard / 3 | 首次+retries、仅OSError重试、耗尽传播最后异常；次数/吞错/捕获类型错误 | 2 / 4 |

另有每个项目的 `app/__init__.py`，因此计入包模块后分别为2/3/4个模块。公开方法合计24，隐藏方法合计48，subtest/循环输入不冒充额外方法数量。Reference Fix 已知跨文件设计任务共5项（CLI优先级及4个Hard）；评分不要求模型复制参考Diff，其他符合契约的实现同样可以成功。

目录：

```text
evals/coding_benchmark/
  manifest.json              # 可信任务索引，不进入Agent
  fixtures/<id>/            # 公开源码、tests/test_public.py、README、notes
  hidden/<id>/test_hidden.py # 可信隐藏测试
  reference/<id>/app/...     # 可信参考实现，仅验证可解性
```

`RuntimeCase` 只包含id、难度、公开prompt和公开测试argv；公开prompt/README均声明仅修改已有非初始化生产模块、不增删文件且保护测试/说明/初始化文件，不用隐藏的修改约束评分；不包含hidden_suite、reference、expected_source或评分断言。manifest精确字段/版本、唯一ID、路径、文件大小/数量、非零测试数均校验，拒绝符号链接、硬链接和未知资产。源码使用逐级dir_fd/O_NOFOLLOW读取，检查读取前后stat与完整字节。

## 3. 架构、核心文件与调用关系

```text
evaluate_real_coding CLI
  → Limits / 双模式门控 / 显式价格校验
  → load_benchmark → validate_benchmark
      → Buggy public+hidden / Reference public+hidden（独立沙盒）
  → 每个Case、每次Repeat：新建临时Git仓库
      → 公共RuntimeCase → 原AgentLoop + 原CodingTaskController
          → 原Repository/Patch/RunCommand + Phase23 Journal
          → CodingClient → 原TracedClient → 真实SDK或显式离线Client
      → 任务结束，取最后源码和Index证据，关闭Capsule
      → 独立Judge副本 + 可信公开测试 + 私有隐藏测试
      → 原Seatbelt + run_process → 独立计数/通过结果
      → 比较文件、Index、Journal、可信资产、最终版本
  → Coding Metrics → 只含有界元数据的报告
```

| 文件 | 关键函数、数据与职责 |
| --- | --- |
| `coding_fixtures.py`（新增） | `Image/RuntimeCase/Case/Benchmark`、`load_benchmark/snapshot/write_images/create_repository`；只复制公开镜像，真实Git初始化，私有资产严格校验 |
| `coding_judge.py`（新增） | `run_suite/judge_images/validate_case/validate_benchmark/judge/trusted_seal`；Reference与Buggy验证、独立可信测试、版本与文件保护 |
| `coding_live.py`（新增） | `Limits/RequestBudget/CodingClient/live_client/labels`；SDK双门、时间/次数/估价、Usage和安全标签 |
| `coding_metrics.py`（新增） | `CodingTrace/BenchmarkAgent/case_metrics/summarize/failure_reason`；元数据仪表和独立协议核验，复用原Trace/TracedAgent |
| `coding_benchmark.py`（新增） | `configuration/selected_cases/run_task/evaluate/save_report`；原Loop编排、全新重复任务、生命周期与报告 |
| `evals/coding_benchmark/**`（新增） | 12项公开项目、隐藏测试、Reference Fix、manifest |
| `scripts/evaluate_real_coding.py`（新增） | 默认离线CLI，严格Live双标志、价格文件和独占报告保存 |
| `scripts/coding_benchmark_demo.py`（新增） | 单个TTL公开契约的离线策略，演示四条正反路径，不读取Reference Fix |
| `scripts/check_real_coding_eval.py`（新增） | 专项回归，真实临时文件/命令/沙盒、模拟SDK边界与独立评分 |
| `scripts/check_phase.py` | 将新专项加入全量入口 |
| README、阶段索引、本学习文档、AI_HANDOFF | 用法、真实状态、学习与交接 |

上述模块均位于 `mybot/evaluation/`。没有修改原Loop、Controller、Session、Registry、Patch/Command、Sandbox或MCP代码，也没有修改原生Tool Schema。

## 4. Benchmark有效性与Gold隔离

正式评测前，对全部12项执行4个独立检查：Buggy公开、Buggy隐藏、Reference公开、Reference隐藏。每项Buggy必须至少有隐藏失败，Reference必须公开和隐藏全部通过，发现数量必须非零且符合可信资产。参考实现失败标记invalid_benchmark_case；评分进程/沙盒异常标记grader_error，两者均不是模型错误。

首次验证结果：12/12有效；公开Baseline均2项通过，隐藏Baseline每项至少1失败；Reference公开24/24、隐藏48/48通过。公开测试故意覆盖普通回归，隐藏测试覆盖边界和交互；公开通过不等于整个功能正确。

验证结果可在同进程内做有界元数据缓存，键包含资产SHA、可信评分代码seal、Python/平台和沙盒可用性；仍每次校验资产与代码完整性，实际Judge每次重新验证沙盒。缓存不保存Gold到模型上下文，跨CLI进程不继承缓存。

Agent目录只含公开镜像和独立.git。hidden/reference在允许Workspace之外。文件工具拒绝越界，模型命令的Seatbelt只允许当前公开Workspace、专用运行临时目录和固定Python运行时；隐藏资产根不在读白名单。专项实际请求读取本仓库隐藏文件，得到PermissionError，没有将正文送回模型。

Agent结束后才在另一个临时目录重建最终项目：生产源码使用最后快照，公开测试/包初始化等受保护内容始终来自可信资产；随后注入隐藏测试。隐藏输出不回传ToolResult、Session、Controller、Prompt或下一轮请求。Reference只用于可解性验证，不作为Agent Patch、不提示模型下一步工具。

## 5. 独立工作区与生命周期

每个Case/Repeat拥有新Git仓库、Index、Session、Controller、Registry、Context和Journal，不从上一个任务继承文件、对话、审批或Undo Capsule。可信fixture setup用固定本地Git命令创建基线提交，禁Hooks、全局/系统Git配置和外部Filter路径，不Fetch/Clone或访问网络。模型没有新增Git写权限。

Evaluation运行时强制：coding开启、patch write、autonomy开启、git_workflow开启而undo关闭；macos_readonly；MCP/Skills/Session持久化/Debug关闭；原生Patch-only Registry。正常Gateway默认配置不被覆盖，真实config/config.json不被修改。

不提供任意用户仓库导入选项。临时目录按每任务和整次运行上下文清理；取消/异常先由原进程生命周期清理，再释放文件和内存引用。报告只保存结果元数据，未保留工作区、原始对话或私有镜像。

模型自主选择调查路径，Harness没有规定search→read→patch→test固定顺序；`BenchmarkAgent`只覆盖工具边界作仪表，`_handle_message`来自原AgentLoop。原Controller继续处理预算、写入次数、重复操作、审批停止、revision和测试证据。

## 6. Agent状态与Judge状态

Agent state保留原Controller结论：verified、edited_unverified、completed_without_changes、blocked、budget_exhausted、execution_uncertain等；它只说明模型自己的指定测试证据。

Judge state独立为hidden_pass、hidden_fail、invalid_case、grader_error、unscored。不能将Provider错误、沙盒不可用、评分器超时/零测试/不完整回执转换成隐藏测试失败。候选代码导入或语法错误由可信loader记录为候选测试失败，不冒充基础设施故障。

`verified_repair_success`要求：基准有效，真正修改生产代码，可信公开回归和隐藏测试均通过，受保护/无关文件无非法变化，Index/HEAD未改，Journal与实际变化相符，没有执行不确定/协议误验证，评分完整且属于最后源码。它不要求Agent内部state一定verified，因此可以区分实际修复却未按要求测试，以及公开通过但隐藏失败。

独立协议仪表记录真实原生Patch发布哈希、修订、命令前后哈希、批准/启动/完成/Seatbelt/退出/非零测试数，不能仅相信Controller计数或模型文字。`protocol_false_verified_count`表示违反Phase22自己的条件却标verified，必须为0；`hidden_failure_after_agent_verified`则允许大于0，通常表示公开覆盖不足或修复不完整。

多文件变化取完整最终文件快照，不从Journal声称的路径推断；检查保护路径、额外文件、模式、Index与完整Git元数据、Journal归属。Judge期间结束再检查Agent目录未变；变化会使成功失效，标记stale_final_version。测试后再次Patch会使原验证失效，不把旧测试算到新代码。

## 7. Judge执行与防虚假成功

Judge同样执行可能不可信的最终代码，因此使用原Phase21真实隔离探针、Seatbelt deny-first profile、固定可信Python、无网络、只读源码/测试、仅专用temp可写、超时/输出/文件额度和进程组清理。自检失败不降级宿主执行。Judge不是模型工具，不向Agent开放。

可信bootstrap先加载unittest，候选stdout/stderr和测试详细日志送到devnull，最后只产生带随机回执、实际测试计数、失败/错误/skip和完整性标记的结构化结果。普通打印“Ran ... OK”、exit0无回执、零测试、跳过、截断、信号终止和超时均不能提供成功证据。模型最后一句话完全不进入评分规则。

隐藏/公开测试来自可信文件，模型改公开断言不能获分；Judge使用原测试，另将测试变化记为保护违规。可信资产和5个评分模块的磁盘seal要保持一致；bootstrap检测unittest关键函数/类对象被覆盖，常见monkeypatch会成为grader_error。隐藏测试副本只读，专项实际验证写入被拒绝。

这些不是形式化反作弊证明。候选代码与unittest在同一个Python解释器内执行，任意同进程反射、复杂状态操纵或未知系统问题仍可能影响测试；隐藏资产在Judge阶段可供可信测试执行，并不构成对同进程候选代码的机密内存隔离。Agent已结束，Judge结果不回传模型。若将来评测主动对抗代码，需要进程外语义断言/更强隔离设计，不能把本阶段包装成完全抗恶意测试系统。

## 8. Live双确认、Provider与预算

默认完全离线，不构造SDK，不调用真实API。Live必须同时指定 `--live --confirm-api-cost`；只给其一、缺凭证/模板Key、非TTY或沙盒未验证都拒绝。开发/自动化只模拟SDK，不实际发付费请求，未来真实运行必须用户另行明确授权。

复用GatewayConfig/build_client和chat.completions.create；SDK max_retries=0，单次计数没有隐式重试。Live禁止离线Client和合成自动审批Provider覆盖，模型每次run_command仍使用原cli_command_approval精确yes独立批准。没有审批或TTY不能自动执行。启动前显示安全Provider/Model、Case/Repeat、全局请求/总时间上限、价格是否配置、逐次批准要求和沙盒状态，无凭证和base_url。

默认仅本次Evaluation作用的限制：max_cases=2、repeats=1、max_requests=24、每Case模型请求12、输出2048 Tokens、task240秒、total900秒、request45秒、Judge10秒、seed24。均严格检查类型/范围，不偷偷扩大预算。原Controller继续保留48工具/3Patch写入/6命令/3无进展等默认限制。

全局门在真正API调用前检查请求、总期限及已知估价。每任务还有Controller预算与外层等待时限。记录尝试请求、成功响应、API失败数和取消数；失败包含本地取消/超时的未完成调用，不证明服务端未执行或未计费；达到上限后不再请求，剩余任务unscored。任务取消仍先安全清理，原同步Patch事务和交互input线程不能被任意中途硬停，时间限制不是跨所有阻塞边界的实时硬保证。

不支持工具/Schema/legacy function_call、空/重复Call ID或异常响应结构明确provider_unsupported；SDK异常只使用受信任status/code分类provider_error/provider_timeout，不保存SDK原文、URL或环境变量。不更换模型/供应商，不回退固定Client伪装Live。

## 9. Token、费用与报告

复用usage_values/token_totals/validate_prices/estimated_cost。input/output/total/cached Tokens来自服务端Usage；缺失、部分失败或未知缓存信息保持null，不用Schema字符估Token。Schema字符单独统计真实请求。

价格由用户显式本地JSON提供，无内置模型价格表；currency、输入/输出/缓存每百万价格严格校验。未配置价格或必要Usage缺失，成本null。指定max-estimated-cost却没有价格会拒绝；已请求后Usage/费用未知则停止后续请求，不能将未知当0。最后一次响应可能超出估价限制，这不是账单硬限额。真实账单不在本阶段数据源内，费用每成功样本均值只有总估价和成功分母均已知才计算。

报告分组：

- 修复：total_cases（Case×Repeat）、attempted_cases（已进入Agent）、eligible_cases（完整有效评分）、hidden_pass/verified_repair、全体尝试修复率和有效评分修复率；基础设施失败仍在全体尝试分母中，不靠剔除失败抬高主修复率。
- 声明/验证：agent_verified、hidden_pass/hidden_failure_after_agent_verified、edited_unverified、premature_completion、false_success_claim、verification_expired、protocol_false_verified。false_success_claim是宿主verified与完整Judge修复不一致的计数，不用主观NLP推测模型最后一句的意图。
- 工具：search/read、preview/write/commit、命令、真实测试、重复、stale、拒绝、沙盒和预算停止；重复次数不等于更深入思考。
- 资源：实际请求、Token、Schema字符、耗时、显式估价及成功成本；未知null不参与已知均值。
- 保护：unrelated/protected/index、越界、拒绝、execution_uncertain、Call ID配对、Journal归属不一致。

multi_file_repair_rate基于有已知多文件参考设计的任务，和difficulty分开；允许其他正确实现。没有真实Provider成功响应或有效评分时也不生成模型能力率。离线始终ability_score=false，所有能力率null，具体安全机制计数仍可展示。

可重复性包含benchmark/grading版本、全资产SHA、mybot_commit/工作区Dirty、评分代码SHA、uv.lock SHA、OS/Python/架构、显式价格及估价上限、Provider/Model安全标签、execution_mode、limits/repeats/seed、UTC创建时间及Case IDs。seed只决定未显式选Case时的任务顺序，不承诺Provider采样确定性；显式case_ids按指定顺序。每个Repeat独立，无历史传递。多模型比较必须同数据/隐藏测试/预算/依赖/平台/规则，不能把不同预算直接当公平对照。

Trace复用原Trace/TracedClient/TracedAgent，仅有界元数据事件、输出长度/SHA和结束状态，不保存Prompt、工具参数/结果正文、思考、源码、原始Patch、环境或凭证。摘要不含HOME绝对路径和隐藏正文；未知新增文件名只保留摘要，可信公开路径可显示。`--save`复用原独占保存函数，写入独立`runs/coding_benchmark`目录，不覆盖旧文件；report_type=coding_benchmark，旧报告读取逻辑不变。默认无原始对话转储和自动上传。

## 10. macOS / Python3.12+ / uv 实操

```bash
uv sync --frozen
uv run python -m compileall -q mybot scripts
uv run python -m scripts.check_real_coding_eval
uv run python -m scripts.evaluate_real_coding             # 默认最多2项，只做机制验证
uv run python -m scripts.evaluate_real_coding --max-cases 12
uv run python -m scripts.coding_benchmark_demo
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
```

旧专项/基准：

```bash
uv run python -m scripts.check_git_workflow
uv run python -m scripts.check_autonomous_coding
uv run python -m scripts.check_command_execution
uv run python -m scripts.check_patch_editing
uv run python -m scripts.check_repository_tools
uv run python -m scripts.check_approval
uv run python -m scripts.compare_tool_discovery
uv run python -m scripts.compare_tool_retrieval
uv run python -m scripts.compare_adaptive_routing
uv run python -m scripts.compare_selective_routing
```

以下仅供用户未来明确授权后自行运行，本阶段未执行：

```bash
uv run python -m scripts.evaluate_real_coding \
  --live --confirm-api-cost --case-ids cache-ttl-001 \
  --max-cases 1 --max-requests 12
```

CLI还支持repeats、max-model-requests-per-case、max-output-tokens、task/total/request/judge-timeout、seed、prices、max-estimated-cost及save。先在本地真实配置填写Provider/Model/凭证，绝不提交config/config.json。正常助手仍用 `uv run python mybot/main.py`；Evaluation独立创建合成仓库，不修改配置中的真实Workspace。

## 11. 四条离线演示与真实结果

Demo只给一个TTL教学策略，读取真实文件/SHA，提交原生Patch，实际运行公开测试；策略根据公开契约处理边界和负TTL，没有获得所有任务Gold，也不负责决定Judge成绩。

| 路径 | Agent state | Judge state | repair_success |
| --- | --- | --- | --- |
| 正确修复 | verified | hidden_pass | true |
| 仅修边界遗漏负TTL | verified | hidden_fail | false |
| 只说“Fixed; all tests passed” | completed_without_changes | hidden_fail | false |
| 注入评分器OSError | verified | grader_error | false |

全部protocol_false_verified=0、real_model_repair_rate=null。最后一条明确是离线注入基础设施异常，不是声称真实沙盒失效。

默认全12项离线运行使用无修复策略：验证全部数据集可解，再跑原Loop/独立Judge；不能将无修改的回复拿到修复分。该路径是机制检查，不是模型能力排名。最终数据集SHA256为 `de4fd3f28acb43ecc89bb5412aa11954f62704b3f2d0c9b60716035bbe288dcd`。实跑12/12任务得到完整评分、12次合成请求、0次Agent Patch/命令、0修复；全部Baseline/Reference有效，四项文件/Index/归属保护异常和protocol_false_verified均0，能力率/Token/费用均null。无修复策略不等于模型失败成绩。

专项目前109项通过，涵盖数据有效性、Gold隔离、真实文件/Index/临时清理、SDK双门/错误/缺Usage、预算与成本、正确/过拟合/伪造/保护/篡改/超时、最终版本、重复生命周期和旧报告。859项全量及Phase1/2原断言已通过；随后补充了只读Git来源/显式价格元数据与公开修改范围，当前109专项再次通过，最新修正源已在APFS预还原副本完成859全量/四基准/12项离线/四路径Demo；正式归档的两份独立副本也已完成同一套验证。Phase19～23专项分别34/55/58/80/101、原审批25均通过；编译与归档脚本集成通过。四基准与Phase23 dfd3461实跑结果除六个计时/Git字段逐字段相同；正式归档与两份独立副本验证现已全部通过。

旧基准数值（与Phase23保持）：Discovery 3案例Eager7请求/409199 Schema字符、Progressive15/52280，均成功；Retrieval 36案例Recall@5 Literal57.8125%、BM25 62.5%、Hybrid87.5%，负例4/4正确；Adaptive12案例Eager25/1461425、Progressive51/175363、Adaptive25/176425，均成功；Selective60路由precision88.8889%、recall97.2222%，负例24/24、多工具覆盖10/12，核心12例27/137582、挑战10例23/109693最终成功，原有遗漏未隐藏。仅排除task_wall_time_seconds、request_latency_seconds、request_latencies_seconds、routing_overhead_ms、git_commit、worktree_dirty六字段。

## 12. 常见问题、限制与阶段变化

- Reference也失败：invalid_benchmark_case，先修基准；不要记为模型失败或把答案回传给模型。
- Agent verified但hidden_fail：公开覆盖不足或修复不完整；只有未满足Phase22自身条件却verified才是协议误验证。
- Provider/Usage不兼容：明确错误或null，不回退、不猜费用。
- Live在非TTY拒绝：保留命令逐次审批边界；不要加入自动approve来绕开。
- Grader异常：独立infra/unscored统计，保留尝试分母，不能虚构hidden_pass或将其全部归咎模型。
- 还原副本没有.git：mybot_commit可能null；其来源用外部Tag/ZIP逐文件验证证明，不伪造本地Git历史。

Phase23→24增加的是Benchmark、受限Live请求适配、隔离Judge和指标；原自主循环/安全工具保持。当前只验证合成任务和机制，不证明真实LLM泛化、复杂仓库表现或对任意恶意解释器的鲁棒性。沿用Seatbelt已弃用、无进程总内存/总磁盘硬配额、脱组后代回收及元数据可见性边界。

本次停在Phase24，不自动Push/Merge/进入25。下一步可由用户另行明确授权有限Live预算，观察同一冻结任务集下的真实失败分类，再决定改进方向；不根据某次模型失败临时修改隐藏标准来美化成绩。无工具行动才使用model_did_not_investigate；已有调查却未改代码记录no_code_change，不用缺少修改臆测没有调查。

## 13. 提交与归档状态

按本次用户更严格的顺序：先提交已验证实现，从该确切提交做临时ZIP-only restore和独立验证；完成后才添加archive-ready，再作就绪文档提交。随后save_phase.sh24创建唯一正式annotated Tag/完整ZIP，不覆盖旧Tag/ZIP。正式ZIP须核对外置盘实际路径，并独立APFS解压与正式restore再次验证。发布事实另作纯文档记录，不移动Tag。

实现提交 `fafab785f9305de9525144e61ffcb95d9796270b`，事件分类/取消计数修正源 `178859f3340c9a00fb9808eed76af3f446af3634`；原Loop/工具未变。

已在添加archive-ready之前，从干净修正源提交生成私有预验证ZIP `/private/tmp/mybot-phase24-preflight-x380wel9/mybot-mini-snapshots/phase-24.zip`，CRC/注释提交SHA/278文件逐字节一致。使用原restore_phase.sh的ZIP-only分支在APFS独立还原到 `/private/tmp/mybot-phase24-preflight-x380wel9/mybot-mini-learning/phase-24`，冻结安装、编译、859全量及原断言、四基准、12项离线和四路径Demo均通过，源码哈希未变；未创建临时Git Tag来伪装正式归档。

预验证ZIP SHA256 `f26f107f0c51c82087c576522c694ac23570f8bc5da99ebe3b78a15998300c6e`，仅为私有验证副本，不是正式phase-24归档。最新代码已完成独立集成回归，因此现在可以添加就绪标记。正式Tag/ZIP及双副本验证已经完成，确切发布事实见下节；Tag保持原位。


## 14. 正式归档与最终验证

- 实现提交 `fafab785f9305de9525144e61ffcb95d9796270b`；事件分类与取消计数修正 `178859f3340c9a00fb9808eed76af3f446af3634`。
- 归档就绪提交/Tag所指源 `3f53b0562c22ce3727d9ffe403880be74dbbd5e1`；唯一annotated Tag `phase-24`，Tag对象 `43c325fe77fed6d48ef9cc0844a957e742c272e7`。本节是后续纯文档记录，未移动Tag或重新导出归档。
- 完整ZIP `/Volumes/move-disk/data/code/mybot-mini-snapshots/phase-24.zip`；脚本原始输出 `/Users/godblack/.codex/worktrees/phase-24/mybot-mini-snapshots/phase-24.zip`。二者SHA256均为 `3c69bb4eb29d982f3f8a9b1c1ea9fe968e098f1e58d3d5a04b8ca7a3fc5f8e09`。
- ZIP共373条目、278个文件，CRC正常，ZIP注释等于源提交；全部源码逐字节与Tag一致，不含AppleDouble、真实配置、凭证、Session、虚拟环境或缓存。
- 外置盘正式ZIP在APFS独立解压到 `/var/folders/7p/n7p6_hdd08j48k1kbg6kjnvh0000gn/T/mybot-phase24-official-zip-erbp3ik2/source`；原restore_phase.sh24还原到 `/Users/godblack/.codex/worktrees/phase-24/mybot-mini-learning/phase-24`，未覆盖已有目录。
- 两份正式副本分别完成`uv sync --frozen`、mybot/scripts编译、859项全量及原Phase1/2断言、四旧基准、12项完整离线和四条Demo，均通过。测试前后278个源文件哈希及文件集合完全相同；四基准与Phase23除已列六字段一致。
- 每份评测均验证12个Buggy Baseline隐藏失败、12个Reference公开/隐藏通过；无修复离线策略不授予修复分，能力率/Token/费用null。隐藏隔离、文件/Index/归属保护、协议检查无异常。
- 原main `3461dc7031bb9542070b034bed0be47f61760f75`、用户app.py/USER.md、原Index、24个旧Tag对象和全部旧ZIP字节均保留；开发只在codex/phase-24进行。未Push、未Merge、未进入Phase25。
- 没有调用真实LLM或产生实际API费用。Seatbelt/进程资源边界、同进程Python测试防作弊局限和估算成本非硬账单上限仍如上文；真实Provider兼容性、模型修复率/成本/稳定性尚未实测。

**真实模型 Coding 能力尚未实测，当前完成的是安全、可重复、支持真实模型的 Benchmark 评测系统。**

## 15. 首次Live反馈：审批通道与Patch版本提示修复

基线`codex/phase-24` / `571e7d8`。本地既有报告`runs/coding_benchmark/live-20261019T134803-ec1eaddc.json`记录`coco / deepseek-v4.1-flash`在config-default-001实际请求6次、工具9次、Token15991（输入15410、输出581），费用因没有价格而null。工具为list_files×3、read_file×4、apply_patch×1、run_command×1；没有read_file_range或Patch预览，写入被stale_file_hash拒绝，命令审批拒绝，最终blocked，公开2项通过、隐藏4项未全过、无成功修复。此结果含Harness问题，不能全部归咎模型能力。

### 审批输出通道

原run_task用redirect_stdout(StringIO())屏蔽Agent输出，原审批同时检查sys.stdout.isatty()，导致外层是真TTY而内部必然拒绝。现在Live在捕获前绑定调用者stdout到原cli_command_approval的可选host-only output参数；审批提示、完整受检命令、警告和输入提示仅写该通道，并在读取输入前flush。stdin和所选输出都必须是真TTY；不回退__stdout__或/dev/tty，不伪造isatty，不缓存批准，不自动输入yes。每次仍须精确yes，拒绝/EOF/异常沿原授权路径停止。

Agent原始输出继续在Live和Offline中捕获，避免通过取消捕获暴露源码、工具正文或模型输出；报告仍只有有界元数据。MCP Approval、Seatbelt、Registry/Tool Schema与命令逐次审批语义保持。

### Patch版本约定

read_file_range在Patch模式由Registry设置include_version=true，对读取的完整原始文件字节计算file_sha256；截取/编号后的行文本不是哈希输入。ApplyPatchTool的expected_sha256必须与当前完整字节匹配，错误哈希仍被stale_file_hash拒绝。

仅在CodingTaskController自主编码instruction补充：先用read_file_range获取metadata.file_sha256，复制到expected_sha256，不猜测哈希；建议dry_run=true预览，再dry_run=false写入；stale_file_hash后重新读取当前版本并重建Patch。未修改工具参数、Patch安全检查、Benchmark Gold或非自主默认模式；提示只是指导，不能保证模型必然遵守。

### 离线回归与后续

新增7项：真实PTY中的原Loop/Controller/Journal/Judge审批与修复链路；拒绝停止；逐次精确yes且无复用；非交互拒绝；Offline捕获且不构造Live Client；完整文件SHA与旧读取模式；错误SHA拒绝后重新读取、预览、写入和实际测试。PTY与合成用户输入仅用于离线回归，模型为模拟Client，不发真实API。测试同时检查原始输出/凭证哨兵不泄露、Index和Journal归属、最终Judge及协议证据。

针对性7项、Phase24专项116项、命令58项、自主编码80项、MCP审批25项及编译通过；`uv run python -m scripts.check_phase`全量866项通过（原859项全部保留+新增7项），原Phase1/2断言亦通过。完整日志在本机`/tmp/phase24-fix-full.log`，未作为原始运行日志提交。原main、用户修改、原Index、配置、已有Live报告和全部Tag/ZIP哈希保持不变。

当前未运行新的付费Live；须用户确认后才重新执行案例A，不自动进入案例B或Phase25，不Push/Merge。原phase-24 Tag/ZIP不移动或覆盖；本次修复不在旧归档内，源码以后续Commit为准。非交互运行仍须拒绝，不因为本次修复开放自动审批。

## 16. Live命令超时约定与独立结果呈现

修复基线`89a3737`。既有本地报告`runs/coding_benchmark/live-20261019T142215-f2814615.json`记录config-default-001使用deepseek-v4.1-flash，请求8次、工具11次，真实Patch预览和写入各1次；Judge公开2项、隐藏4项全部通过，verified_repair_success=true。但Agent状态blocked、stop_reason=timeout_exceeds_configuration、Agent测试0次，原顶层failure却为null。报告不保存原始命令参数，因此不能从现有元数据断言模型当时具体请求了多少秒。

### 配置、Schema与提示的一致性

coding_benchmark.configuration原本就将单命令最大/默认超时固定为30秒；任务300秒、全局600秒或API请求45秒不改变这项安全限制。RunCommandTool省略timeout_seconds时使用自身CommandSettings.timeout_seconds，明确请求超限时在审批/进程启动前拒绝；Controller另按剩余任务预算约束已批准命令。

缺陷在于原通用Tool Schema只暴露整数1～60秒，自主提示也未给出当前配置。现在每个RunCommandTool实例独立复制参数Schema，将timeout_seconds.maximum/default设置为该实例经过验证的实际配置，并建议省略参数；不增加参数名或必填项，不改变默认执行方式。类级通用输入范围和明确的host上限检查保留，因此旧输入错误分类保持，配置30秒时请求31～60秒仍返回timeout_exceeds_configuration，而不是静默截断或自动重试。

CodingTaskController每轮直接从原生run_command.settings读取command_timeout_seconds写入动态约束，建议省略timeout_seconds，不把任务/API超时当作命令上限。提示和Schema没有硬编码30；离线测试验证1/7/30/60秒配置互不污染，Phase24配置仍严格30秒。原Live终端审批输出通道、真实TTY、每次人工yes、Seatbelt和非交互拒绝不变。

### Judge修复与Agent工作流是两个维度

保留judge.verified_repair_success的原含义和评分规则，不将它改成Agent是否完成测试流程。新增每案例agent_workflow_success，仅在Agent verified且协议证据和Tool Call ID配对有效时为true；聚合新增agent_workflow_success_cases及agent_blocked_count。已有agent_state、controller.stop_reason仍保留。顶层failure在完整Judge有效且Agent blocked时保留Controller停止原因，不再被Judge修复成功清空。verified_repair_cases只表示独立Judge修复成功，不能据此声称Agent工作流已完成。

离线重现明确得到：真实Patch写入、Judge公开/隐藏通过及verified_repair_success=true；同时Agent blocked、agent_workflow_success=false、real_test_runs=0、failure=timeout_exceeds_configuration。报告保存/读取保留两组事实，没有修改Gold、隐藏测试、Reference或修复率分母。

### 验证与限制

新增4项专项测试：动态Schema/提示与配置相符；超限值审批前拒绝且不截断；合法30秒经真实PTY的逐次审批、Seatbelt与unittest；Judge修复成功和超时blocked同时呈现及保存。原有省略超时的终端链路也新增Schema/default/提示/批准超时断言。PTY和模拟人工输入仅用于离线合成模型回归，不用于付费Live。

针对性5项（4项新增及既有默认终端链路）、Phase24专项120项、命令执行58项、自主编码80项、编译均通过；`uv run python -m scripts.check_phase`全量870项及原Phase1/2断言通过，包含866个既有用例与新增4项。旧Schema固定60秒的断言更新为实际上限/default及其余原生结构不变检查，未删除既有用例。全量日志`/tmp/phase24-timeout-full.log`。main、用户修改、原Index、配置、已有报告及Tag/ZIP哈希核对未变。没有新增付费Live，不Push/Merge、不进入Phase25。模型仍可能忽略提示主动传超限值，此时安全拒绝是预期行为；离线通过不等于真实模型已复测成功。原phase-24 Tag/ZIP保持不变，不包含后续修复。

## 17. Medium预览失败：诊断边界与有界纠正

基线`192fcbd`。已有本地报告`runs/coding_benchmark/live-20261019T145243-391f3475.json`：csv-export-001使用coco/deepseek-v4.1-flash，请求5次、工具9次（list_files×3、read_file×5、apply_patch×1），read_file_range为0；首次Patch预览失败，无实际写入/测试，blocked，stop_reason=patch_failed_without_safe_recovery，stale计数0。五次读取均为旧read_file，没有通过read_file_range取得file_sha256。

**不能从旧Trace还原具体Patch错误。** 原Trace.error_category只识别计划错误，其他工具错误一概other_tool_error；报告未保存Patch或原始参数。本次没有把该错误武断归为invalid_arguments、重叠编辑或无效修改，也没有付费重放来猜测原因。能够确定的是：错误诊断被丢失，Controller因safe_to_retry不是true而立即停止；具体拒绝是否应继续，旧报告证据不足。

### 原错误传递与副作用边界

AgentLoop先做有界JSON解析；失败直接返回preflight_failed、safe_to_retry=false。解析成功才进入ApplyPatchTool：参数校验→逐文件只读预检/生成目标字节→Diff→（仅write）Journal准备与暂存→版本复查→逐文件发布→最终验证→清理。Controller只对真正原生ApplyPatchTool检查safe_to_retry与不确定状态；没有第二个循环。旧_RETRY仅有stale_file_hash、anchor_not_found、ambiguous_context，未尝试发布且清理无异常时可恢复，包含原有正式写入前的版本/锚点冲突；本次保持此集合不变。

status=preflight_failed原本也可能表示写入准备失败，不能单靠该标签推断“从未写过任何字节”：暂存/备份和Journal资产可能已经生成。现在failure_phase明确区分argument_parsing、validation、preflight、preview、write_preparation、publication、cleanup、journal。validation/preflight及Dry Run的Diff不创建暂存/发布；write_preparation可能创建暂存/备份；publication后可能改变一个或多个目标，必须依靠现有回滚与身份/字节验证。cleanup或Journal异常继续按不确定/严格拒绝处理。

### 恢复规则：诊断白名单不等于恢复授权

新增独立_PREVIEW_CORRECTABLE，仅包含invalid_arguments、overlapping_edits、no_effective_changes。它要求dry_run严格为bool true、失败阶段为validation或preflight、没有任何发布尝试；清理异常会覆盖safe_to_retry=false。不是“所有Dry Run失败都可重试”，不是扩大全局_RETRY。

| 情况 | 修改前 | 修改后 |
| --- | --- | --- |
| 已解析、确定是预览的三类纯输入错误 | blocked | running，允许模型在原剩余预算内纠正并重新生成 |
| 正式写入请求的上述三类错误 | blocked | blocked，原安全断言保留 |
| 原stale/anchor/ambiguous冲突且未发布 | running | 保持原规则，重新读取当前版本再构造 |
| 无法解析JSON、无可信dry_run，或未知/资源错误 | blocked | blocked |
| 路径越界、敏感文件、链接、权限/元数据拒绝 | blocked | blocked，即使Dry Run也是如此 |
| 发布失败但已验证回滚 | blocked | blocked，不自动重做写入 |
| rollback_conflict、partial_failure_possible、清理/Journal不确定 | execution_uncertain或原严格停止 | 保持严格停止 |

工具只提供失败反馈，不自动重放调用、不扩请求/工具/写入/时间预算。模型应检查错误、重新用read_file_range读取目标SHA并重新生成；重复相同错误仍由max_no_progress等原预算停止。自主约束现明确要求任何Patch预览或写入前读取真实file_sha256，不猜哈希。新建文件没有既有SHA，add操作的原Schema不变；Benchmark运行契约仍禁止新增文件。

### 安全Trace与验证

只在CodingTrace添加固定PATCH_ERROR_CODES/PATCH_FAILURE_STATES/PATCH_FAILURE_PHASES白名单：错误代码、阶段、状态、safe_to_retry布尔值。未知值分别归为other_patch_error、unknown_patch_failure、unknown_patch_phase，绝不保存任意异常正文、参数、Patch、源码或私有路径；通用旧Trace不改。诊断列表中的安全拒绝代码绝不因此获得重试权限。

新增11项：三类输入及原stale/anchor错误预览无写入证明；正式写入/非输入阶段不扩恢复；Schema/重叠/无变化分别在原Loop纠正→重新读取→有效预览→提交→真实测试→Judge；重复错误在原预算内停止；非法路径/敏感访问、权限拒绝；真实发布与回滚故障；未解析JSON仍阻断；白名单及任意异常/源码哨兵不泄露。没有删除原有安全断言。针对性11项、Phase24专项131项、Patch55项、自主编码80项及编译全部通过；`uv run python -m scripts.check_phase`全量881项通过（原870项全部保留+新增11项），原Phase1/2断言亦通过。日志`/tmp/phase24-preview-full.log`。main、用户文件、原Index、配置、已有Live报告及全部Tag/ZIP哈希已核对保持不变。

本轮无付费Live，不Push/Merge、不进入25；Gold/评分标准不变，原Tag/ZIP不移动或覆盖。旧Medium错误类型仍未知，不能声称本次必然解决了那个具体模型Patch；后续明确授权的真实运行才可利用新分类诊断。

## 18. 首次Hard失败：Planning开销与请求预算指引

基线`5bdfb01`，本轮只分析既有报告并离线验证，没有付费请求。报告`runs/coding_benchmark/live-20261020T044139-f6127fc8.json`显示validation-chain-001使用coco/deepseek-v4.1-flash：12/12次请求、20次工具、2次预览、2次提交、0次Agent测试，revision=2、last_verified_revision=null，budget_exhausted/max_model_requests。独立Judge公开2/2通过、隐藏未全部通过，hidden_fail、verified_repair_success=false。实际仅修改app/normalize.py与app/validation.py，不能将修改了两个文件等同于调用链修复完整。

### 有代码依据的根因与未知范围

安全Trace按请求分组如下，仅列工具名称，不保留原始参数、Patch或源码：

| 请求 | 工具 |
| --- | --- |
| 1 | list_files、git_status |
| 2 | list_files×2、read_file×2 |
| 3 | read_file_range×5 |
| 4、5 | create_plan；update_plan |
| 6、7 | apply_patch预览；写入 |
| 8、9 | update_plan；update_plan |
| 10、11 | apply_patch预览；写入 |
| 12 | update_plan |

五次响应仅管理计划，占请求预算5/12；最后一次未调用测试，下一次before_request即停止。工具调用没有失败，没有审批拒绝、沙盒错误或版本冲突。这证明请求分配不足以完成工作流；**同时隐藏失败证明候选修复仍不完整，不能归因仅为预算不足**。报告不含模型推理、计划参数或最终源码，不能还原模型选择Planning的心理原因，也不能确定具体隐藏失败输入。本轮不读取隐藏测试或参考实现来设计提示。

`context.SYSTEM_RULES`将多步任务描述为可创建计划，`PlanningTool.description`也以multiple operations作为条件；Coding Controller原来未解释多工具编码仍可DIRECT。这可能促成重复的计划管理，但不是能够从报告证明的模型动机。通用Planning的n步成功路径需要create一次、每步start/completed各一次（1+2n个计划调用），**不要求每个调用独占模型请求**。

`AgentLoop`原本按模型响应中的顺序执行调用；metadata工具走PlanningTool，其他执行先检查Plan.execution_error，再执行真实工具、Plan.observe、Controller.observe。create→start→调查，或已获得证据后completed→next in_progress→下一工具，本来就可在同一响应执行。ContextManager只做本地裁剪/摘录和计划状态视图，不额外请求模型。没有必要增加第二个循环、修改状态机或让宿主代填计划操作。

必须等结果的情况包括搜索决定读取路径、读取决定真实SHA和编辑内容、预览结果决定正式提交、写入完成后的当前revision测试、测试输出决定后续修复和最终结论。尤其正式写入与命令不能放同一批次。批处理不允许猜尚未返回的参数、不跳过失败步骤，也不自动重放失败调用。Plan.update仍只接受真实成功工具证据；这只是一般步骤证据，并不理解步骤文字的语义。代码验证始终由Controller的原生命令、真实非零测试数、文件哈希和revision一致性独立判断，计划完成不生成测试证据。

Controller原提示虽有used/max计数，却没有剩余请求、临界优先级或为测试/结果审查预留的指引。needs_continuation只在模型返回无调用时触发一次，并且同样受原请求预算约束；它既不强制测试，也不能在12次已耗尽后补请求。run_command之后仍需后续响应接收和审查结果；若最后一次请求才发起测试，下一次预算门控仍可能停止任务。这解释了已提交Patch仍可能没有测试机会，或缺少收尾请求。现有finish/can_verify和独立Judge没有把Plan完成当成修复验证；无需改评分。

### 最小优化及证据边界

生产代码只修改`CodingTaskController.instruction()`，不改Tool Schema、通用Planning、Loop、ContextManager或评测器：

| 优化 | 行为与证据 |
| --- | --- |
| DIRECT / PLANNED | 明确目标清晰的多工具编码可以DIRECT，复杂依赖仍可少量执行步骤的Plan；离线分别完成实际修复与测试，不能据此证明真实模型选择会改善 |
| 顺序批处理提示 | 描述现有create/start/调查、completed/start/下一工具组合；合成模型6次响应完成三步Plan、预览、写入、真实测试及收尾，证明现有路径可用，不是新增执行权限 |
| 动态请求意识 | remaining=max(0,max_model_requests-used)，Loop在before_request前构造提示，因此明确包含当前待请求的响应；剩余≤3且当前revision缺测试证据时优先级verify_current_revision，否则conserve_requests，充足时normal |
| 测试与收尾 | 提醒保留必要修复、批准测试、结果审查的请求，避免纯计划响应；本地合成模型在剩2次时响应状态执行真实测试、最后1次审查结果，同样4次上限下可verified；忽略提醒仍严格预算停止，不强行调度或额外留配额 |
| 调用链意识 | 通用说明入口→转换→验证→返回及调用方使用修复结果；不含具体案例文件、答案或隐藏信息，只提高调查机会，尚无真实模型效果证据 |

`current_revision_test_required`仅由已提交Patch、当前verification和last_verified_revision计算；提示不增加证据、不读取隐藏数据、不进入报告。既有verification_required_now的continuation语义保持。未验证补丁、测试失败、预算不足仍不能verified；即使工作流verified和计划全部完成，独立隐藏失败仍是修复失败。

### macOS + uv验证与限制

新增15项离线回归：动态剩余数/临界值/无请求副作用；真实测试和后续写入使优先级随revision变化；DIRECT五次请求修复；三步PLANNED六次响应；无证据/仅预览不能完成步骤；失败不能跳过；计划metadata不能掩盖多副作用批次；合成模型低预算优先测试；忽略提示仍预算停止；已完成Plan有Patch无测试不能verified；失败测试不被完成状态掩盖；提示通用且仅含状态；两文件预检失败无写入及成功提交单revision；计划完成而Judge隐藏失败，报告不含计划敏感哨兵。

运行命令（全部离线，不使用Live参数）：

```bash
uv run python -m scripts.check_autonomous_coding
uv run python -m scripts.check_planning
uv run python -m scripts.check_patch_editing
uv run python -m scripts.check_real_coding_eval
uv run python -m compileall -q mybot scripts
uv run python -m scripts.check_phase
```

专项自主编码94、Planning12、Patch55、Phase24评测132项全部通过，Python编译通过；`uv run python -m scripts.check_phase`全量896项通过（原881+新增15），原Phase1/2断言亦通过，包含命令58项、Git工作流101项及真实TTY/Seatbelt安全回归。全量日志`/tmp/phase24-budget-full.log`。原881项测试保留，未删除或弱化已有断言；涉及两个测试文件的既有211个测试方法通过AST逐项比对保持不变。安全实现、预算配置、Benchmark/Gold/Reference/隐藏测试、Judge、原Tag/ZIP均不改；原有审批输出真实TTY通道保留，离线模拟审批仅用于测试。新增提示会增加每次请求的上下文，尚未测量真实Token净变化；模型也可能忽略提醒。下一轮需用户另行授权，在原12次预算内单次复测，仍同时检查Agent、Judge与当前revision测试证据；本轮离线通过不意味着Hard真实修复成功。

## 19. run_command cwd契约说明与离线安全验证

### 诊断事实与学习目标

基线`f20999c`。既有报告`runs/coding_benchmark/live-20261020T141547-afa40771.json`使用coco2/gpt-6-astra、请求超时90秒：7次请求全部响应，预览1次、提交1次，修改conversion.py、parser.py、service.py；独立Judge公开2/2、隐藏4/4通过。第7次调用run_command却在审批前被cwd校验拒绝，Agent blocked/invalid_cwd、Agent测试0次，revision=1、last_verified_revision=null，不能宣称完整工作流成功。没有出现审批提示或实际启动命令，Codex代输入yes为0次。

报告只保留脱敏状态，不含原始cwd，**不能猜模型传了绝对路径、上级目录、失效路径或其他哪种具体参数**。可以确认的缺口是工具只暴露cwd的string长度约束，没有合法形式或默认根目录说明；Controller也只讲命令超时，未解释cwd。模型传非法参数不等于路径校验实现错误。本轮只修复模型可见契约，不改变安全边界，不做付费Live。

### 原契约与调用顺序

```text
AgentLoop解析参数
  → RunCommandTool输入包络、命令超时检查
  → _cwd(args.get('cwd', '.'))
      → 拒绝绝对路径和任何..片段
      → RepositoryTool.resolve → FileTool._resolve，约束Workspace和敏感路径
      → 检查路径各部分无符号链接，目标是已存在目录
  → 打开目录描述符、记录身份、解析固定运行时
  → 单次命令审批
  → cwd/目录身份/运行时复检
  → Seatbelt真实隔离自检、创建只读Workspace配置
  → 再次复检、Controller剩余任务预算检查
  → 启动真实进程、解析输出和测试证据
```

cwd原本可省略，默认`.`是工具的Workspace根目录；在Benchmark中是本次隔离案例根目录。显式值只能是已存在的工作区内安全相对目录，如`.`或确实存在的`src`，不是宿主项目路径或临时案例的绝对路径。绝对路径、`..`片段、符号链接、缺失目录和普通文件均拒绝，敏感目录继续由RepositoryTool拦截。跨工作区符号链接也可能在共享解析器处提前拒绝，不能假定所有拒绝都使用同一个错误码。

原参数校验先于审批和启动，审批后复检防止目录或运行时变化；任何未完成原生命令仍由Controller严格blocked或execution_uncertain停止，同响应后续调用获得配对的停止结果，不能自动修正或重试cwd。真实测试成功仍须匹配当前revision和文件SHA，cwd合法本身不会产生验证证据。

### 最小修改与兼容性

生产文件只有`mybot/tools/run_command.py`和`mybot/agent/coding_controller.py`：

| 项目 | 修改前 | 修改后 |
| --- | --- | --- |
| 工具description | 无cwd使用建议 | 推荐省略，显式值使用已存在的安全工作区相对目录 |
| cwd Schema | string、minLength=1、maxLength=4096 | 保留类型/长度，添加description及文档default="."，不新增required或收紧输入包络 |
| Controller指令 | 无cwd约定 | 紧凑提示省略优先、隔离根目录、禁止绝对宿主/临时路径、..与符号链接 |

JSON Schema的default是文档注解，不注入参数，也不静默纠正非法值。方法仍使用原`args.get('cwd', '.')`，不改变旧模式的默认行为。新测试验证原Schema接受的路径字符串仍可通过同样的JSON类型/长度检查，再由原运行时路径安全规则判断。RunCommandTool全部方法AST与基线一致，含_cwd、execute、failure_result、审批后复检；共享解析器、Loop、审批Provider、Seatbelt、30秒命令上限、command_fatal、自动重试限制和Controller证据规则不改。指令不含具体Benchmark答案或文件名。

### 离线回归与结果边界

新增9项测试：

- 命令4项：Schema说明/default及输入范围不变；省略cwd与`.`各自执行根目录真实Seatbelt unittest；已存在`src`执行真实unittest；非法绝对/..、缺失/文件、内部/外部及中间符号链接和敏感目录均在审批、运行时解析、隔离探测与进程之前拒绝，无执行证据。
- 自主编码3项：Controller通用提示；非法cwd仍fatal、不自动修正/重试、后续工具停止且ID配对、报告不泄露参数；显式`.`的真实沙盒测试后仍由新revision和外部文件哈希变化使旧证据失效。
- 评测2项：合成模型省略cwd，经原Loop、逐次审批、真实Seatbelt/unittest、Journal、Judge完整通过；另一路真实Patch通过Judge而非法cwd仍blocked、测试0次，原始cwd敏感哨兵不进入报告。两者均断言不构建真实SDK。

macOS + uv命令（全部离线）：

```bash
uv run python -m scripts.check_command_execution
uv run python -m scripts.check_autonomous_coding
uv run python -m scripts.check_real_coding_eval
uv run python -m compileall -q mybot scripts
uv run python -m scripts.check_phase
```

新增针对性9项、命令62、自主编码97、Phase24评测134项及编译通过；`uv run python -m scripts.check_phase`全量905项通过（原896+新增9），原Phase1/2断言亦通过，包含真实TTY审批、Seatbelt和Git工作流101项安全回归。三个测试文件原有284个测试方法AST比对保持不变，没有删除或弱化已有断言。配置coco2、API Key、端点、模型、既有报告、main、用户文件与原Index、全部Tag/ZIP哈希核对保留；Benchmark/Gold/Reference/隐藏测试、Judge、请求预算不改，旧归档不覆盖。日志`/tmp/phase24-cwd-full.log`。

这是契约说明优化，不会让既有非法cwd变合法，也不能从旧Trace追溯模型具体参数。离线证明默认/相对目录和原安全执行流程可用，**不代表真实模型一定会按提示省略cwd**。下一次Live须用户另行授权，可继续使用gpt-6-astra；本轮不执行、不重跑、不Push/Merge、不进入Phase25。

## 20. apply_patch预览到提交的参数契约

### 已知失败与不可还原的信息

基线`946ac20`，本轮只做离线调查与通用说明优化。历史报告`runs/coding_benchmark/live-20261020T145953-eb85cef0.json`：error-retry-001使用coco2/gpt-6-astra，11次模型请求全部响应、21次工具；create_plan=1、update_plan=3，4次请求仅管理计划。第10次Patch预览成功，第11次正式写入尝试返回invalid_arguments、failure_phase=validation、safe_to_retry=false，Controller blocked/patch_failed_without_safe_recovery。没有成功提交或Agent测试，revision=0，Judge评估未修改基线，不能据其隐藏失败推断预览中的修复是否正确。

这证明正式调用没有通过本地参数契约，不能证明预览与写入的changes相同、哪个字段错误、是否增删字段或改变类型。报告不保留原始参数、Patch、源码或任意异常正文；本轮不追溯猜测，也不读取Gold、参考实现或隐藏测试来设计提示。现有Schema已完整列出结构和约束，能确认的改进空间是操作说明缺少“预览通过后如何保持同一changes提交”，不能声称说明缺口已经被证明是那次错误的唯一原因。

### 分阶段传递与safe_to_retry规则

| 阶段 | 实际调用与含义 | 安全边界 |
| --- | --- | --- |
| argument_parsing | Loop原生分支先用parse_object检查原始字节、UTF-8、JSON/重复键、有限值、深度/节点等，返回独立有界快照 | 失败未进入工具，无可信完整模式，safe_to_retry=false |
| validation | ApplyPatchTool以该phase起步，bounded_arguments再次检查大小/结构，再由RepositoryTool.validate执行完整JSON Schema；随后检查平台和写模式 | 仍未进入文件预检；历史invalid_arguments定位到此本地校验阶段，无法定位原始字段 |
| preflight | 解析安全路径、只读文件、校验SHA、唯一锚点、非重叠编辑、大小和有效变化，构造目标字节 | 尚未暂存或发布；版本/锚点冲突保留原有可恢复规则 |
| preview | 构造有界Diff；dry_run=true在此返回 | 不写文件、不产生Controller修订或测试证据，也不授权写入 |
| write_preparation | 仅显式dry_run=false且patch_mode=write：Journal准备、暂存、备份、元数据/字节验证，发布前复查全部版本 | 可能已有临时/Journal写入，不能仅凭preflight_failed状态断言无任何暂存副作用 |
| publication | 单文件replace/link发布、重检、必要时_recover | 保留单文件原子替换及多文件预检/既有尽力回滚边界，不承诺跨文件崩溃原子性 |
| cleanup / journal | 清理临时资产、记录归属与失败状态 | 异常继续覆盖可恢复标记；回滚冲突/状态不确定严格停止 |

`validation`是代码设置的阶段标签，不等于原始JSON解析失败，也不等于任何写入后异常。工具Schema对dry_run只接受bool，默认true；正式写入只通过显式false开启，还须宿主patch_mode=write。没有“通过预览就自动提交”的状态或缓存。

原_RETRY保持stale_file_hash、anchor_not_found、ambiguous_context；在没有发布尝试且清理正常时可由模型重新读取并构造新调用。独立_PREVIEW_CORRECTABLE仅对严格dry_run is True、validation/preflight阶段的invalid_arguments、overlapping_edits、no_effective_changes开放纠正。**正式写入invalid_arguments即使发生在文件写入之前，也不满足这两类规则，继续safe_to_retry=false并停止。** 本轮不扩白名单、不修正参数、不自动重放成功预览。CodingTrace继续仅记录固定错误/阶段/状态及布尔值，未增加原始数据。

### 最小通用说明优化

只改`mybot/tools/patch.py`和`mybot/agent/coding_controller.py`的模型可见说明：

- 原工具说明已有SHA、唯一锚点、预览默认和显式写入标志；现在简明列出update所需op/path/expected_sha256/edits、edit的old_text/new_text、add的op/path/content，以及各层禁止多余字段。
- 为现有dry_run字段增加true预览、false请求正式写入且仍需写权限的说明；为changes增加“目标文件和修改内容均未变时，复用同一changes，只把dry_run改为false；修改changes后重新预览”的建议。
- Controller补充同样的紧凑规则及禁止添加未声明字段；既有SHA/上下文冲突重新读取重建、禁止盲目重放继续保留。

这些是说明，不是新增执行前置状态：原本合法的直接写入仍按原规则处理。完整嵌套Schema去除description后与基线逐项一致，字段、类型、必填项、额外字段规则、数量/大小上限和default都未变；整个Patch模块除工具description/parameters外AST一致，Controller除instruction外AST一致。解析、原子发布、权限/路径、Journal、Revision、命令审批、Seatbelt和预算不变。

预算提示已经说明清晰任务可DIRECT、复杂依赖可少量PLANNED步骤、按顺序批处理计划操作、剩余≤3避免计划独占响应，并为必要修复（包括提交）、真实批准测试和结果审查留请求。本轮不重复堆叠或改变Planning算法。历史计划开销不小，但实际停止原因是写入校验拒绝而非预算耗尽。

### 离线验证、使用方法与限制

新增11项：Patch 6项验证完整操作说明、同一changes的update+add预览/提交、预览无文件变化且不启用写模式、非法dry_run类型、缺失/多余字段与错误edits/SHA及原数量限制、预览后stale时重新读取和预览；自主编码3项验证通用提示及原预算提示单份保留、提交后无真实测试不能verified、预览后非法写入仍fatal且Index/Revision/Journal不变并保持ID配对；评测2项验证合成客户端复用同一changes后原Loop→真实测试→Judge成功，以及一个故意增加字段的写入在validation阶段严格停止且敏感哨兵不进入报告。负例只是该错误类别的离线合成示例，**不是历史原始载荷的还原**。

macOS + uv命令（全部离线）：

```bash
uv run python -m scripts.check_patch_editing
uv run python -m scripts.check_autonomous_coding
uv run python -m scripts.check_real_coding_eval
uv run python -m compileall -q mybot scripts
uv run python -m scripts.check_phase
```

针对性11、Patch61、自主编码100、Phase24评测136项及编译通过；`uv run python -m scripts.check_phase`全量916项通过（原905+新增11），原Phase1/2断言亦通过。三个测试文件原有286项方法AST不变，未删除或弱化既有用例。既有stale/锚点恢复、路径/元数据保护、多文件发布/回滚冲突、真实TTY/Seatbelt、当前revision测试证据、Git工作流101项、Journal和Trace隐私回归均通过。日志`/tmp/phase24-patch-contract-full.log`。

配置、API Key、端点、模型、Benchmark/Fixtures/Gold/Reference/隐藏测试、Judge、请求预算、main、原用户修改和Index、历史报告、Tag/ZIP不改；原归档不覆盖。本轮没有真实模型请求、不Push/Merge、不进入Phase25。可在用户另行授权后用原预算复测error-retry-001；离线通过不等于真实模型一定会复用正确changes，也不能声称必然修复了历史那次具体参数错误。

archive-ready: true

## 21. Phase25开始前的历史审计

截至ff10fb6现存20次Live，9次完整成功覆盖9/12；Hard4/4，尚未测pagination/serialization/file-recovery。最新error-retry报告live-20261020T154523-bbbb9fde.json为coco2/gpt-6-astra、8/8请求、34063 Token、270.763秒、Agent verified/Judge hidden_pass、公开2/2隐藏4/4、提交/测试各1、Revision1/1。之前第20节“没有Live”仅指该次离线开发，不代表最终状态。完整Benchmark、稳定性和生产泛化尚未验证，后续见Phase25；旧Tag/ZIP不移动。
