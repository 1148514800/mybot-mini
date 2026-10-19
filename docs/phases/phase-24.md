# Phase 24：Real-Model Coding Agent Evaluation — 真实模型接口与隐藏测试评测

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

全局门在真正API调用前检查请求、总期限及已知估价。每任务还有Controller预算与外层等待时限。记录尝试请求、成功响应、API失败数；达到上限后不再请求，剩余任务unscored。任务取消仍先安全清理，原同步Patch事务和交互input线程不能被任意中途硬停，时间限制不是跨所有阻塞边界的实时硬保证。

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

专项目前109项通过，涵盖数据有效性、Gold隔离、真实文件/Index/临时清理、SDK双门/错误/缺Usage、预算与成本、正确/过拟合/伪造/保护/篡改/超时、最终版本、重复生命周期和旧报告。859项全量及Phase1/2原断言已通过；随后补充了只读Git来源/显式价格元数据与公开修改范围，当前109专项再次通过，最新确切提交的859全量还将由预还原和正式归档副本再次验证。Phase19～23专项分别34/55/58/80/101、原审批25均通过；编译与归档脚本集成通过。四基准与Phase23 dfd3461实跑结果除六个计时/Git字段逐字段相同，独立还原和正式归档仍待完成。

旧基准数值（与Phase23保持）：Discovery 3案例Eager7请求/409199 Schema字符、Progressive15/52280，均成功；Retrieval 36案例Recall@5 Literal57.8125%、BM25 62.5%、Hybrid87.5%，负例4/4正确；Adaptive12案例Eager25/1461425、Progressive51/175363、Adaptive25/176425，均成功；Selective60路由precision88.8889%、recall97.2222%，负例24/24、多工具覆盖10/12，核心12例27/137582、挑战10例23/109693最终成功，原有遗漏未隐藏。仅排除task_wall_time_seconds、request_latency_seconds、request_latencies_seconds、routing_overhead_ms、git_commit、worktree_dirty六字段。

## 12. 常见问题、限制与阶段变化

- Reference也失败：invalid_benchmark_case，先修基准；不要记为模型失败或把答案回传给模型。
- Agent verified但hidden_fail：公开覆盖不足或修复不完整；只有未满足Phase22自身条件却verified才是协议误验证。
- Provider/Usage不兼容：明确错误或null，不回退、不猜费用。
- Live在非TTY拒绝：保留命令逐次审批边界；不要加入自动approve来绕开。
- Grader异常：独立infra/unscored统计，保留尝试分母，不能虚构hidden_pass或将其全部归咎模型。
- 还原副本没有.git：mybot_commit可能null；其来源用外部Tag/ZIP逐文件验证证明，不伪造本地Git历史。

Phase23→24增加的是Benchmark、受限Live请求适配、隔离Judge和指标；原自主循环/安全工具保持。当前只验证合成任务和机制，不证明真实LLM泛化、复杂仓库表现或对任意恶意解释器的鲁棒性。沿用Seatbelt已弃用、无进程总内存/总磁盘硬配额、脱组后代回收及元数据可见性边界。

本次停在Phase24，不自动Push/Merge/进入25。下一步可由用户另行明确授权有限Live预算，观察同一冻结任务集下的真实失败分类，再决定改进方向；不根据某次模型失败临时修改隐藏标准来美化成绩。

## 13. 提交与归档状态

按本次用户更严格的顺序：先提交已验证实现，从该确切提交做临时ZIP-only restore和独立验证；完成后才添加archive-ready，再作就绪文档提交。随后save_phase.sh24创建唯一正式annotated Tag/完整ZIP，不覆盖旧Tag/ZIP。正式ZIP须核对外置盘实际路径，并独立APFS解压与正式restore再次验证。发布事实另作纯文档记录，不移动Tag。

当前尚未创建Phase24正式Tag/ZIP，本文件没有archive-ready标记；收尾后补充确切提交、路径、SHA和独立验证事实。
