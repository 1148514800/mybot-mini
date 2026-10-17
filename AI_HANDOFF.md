# AI Handoff

## 当前目标与状态

Phase18已完成：新增38项专项、全量422项及Phase1/2原断言通过，编译/归档安全通过；唯一phase-18 Tag/ZIP、APFS验证和独立学习目录还原验证全部通过。不Push、不运行Live、不进入Phase19。保留用户mybot/app.py三处注释和workspace/instructions/USER.md未提交修改；旧17阶段Tag对象/ZIP哈希已核对不变。

## 实现与架构

- selection_policy可选legacy/selective，缺省legacy不增加旧配置默认键；selective必须显式enabled=true+adaptive。两模板保持manual/literal/legacy，真实配置未改。
- relevance.py lexical-evidence-v1：原tokenize/Hybrid别名+固定通用词/复数归一化，操作词不独立作领域证据。Strong需名称/Server领域证据且小目录/低DF/多个名称概念之一，或两个低DF描述概念；Weak/None不选。不读取Gold/用户文件/执行结果，不是概率。
- 同一Router的Selective分支仅取前64正分候选，全部Strong且满足原预算与preselect_limit才small_eager；否则按新增概念/(1+完整Schema相对成本)确定性贪心，零新增不填满。保留完整Schema、两层预算、原子应用、权限及审批。Legacy原路由与AgentLoop不改。
- 新独立60例Routing Benchmark（36正/24负，design/heldout各30），10例独立Agent挑战；旧12核心案例/检索器/词典/Phase9 runner未改。证据规则先冻结再评heldout，无结果驱动调参；后续v1.1只修正Selective small_eager数量契约，35工具基准逐项不变，原heldout已使用。
- Harness显式mode映射新增adaptive_selective_hybrid；独立case_set（默认core）复用原Limits与owner生命周期。新增初选质量/分母/弃选/无关数/多工具覆盖/手动补救；真实builtin要求单独计数，仅排除明确内置文件接口，未知Gold沿旧评分，Canary回归通过。无额外LLM请求、无权限/审批变更。

## 文件

新增relevance.py、evaluation/tool_routing.py、tool_routing_cases.json、tool_agent_routing_cases.json、evaluate_tool_routing.py、compare_selective_routing.py、check_routing_confidence.py、phase-18.md。修改router/discovery、evaluation/tool_agent、evaluate_tool_agent CLI、check_phase、两配置模板、README/索引/本交接。AgentLoop/ContextManager/Planning/Session/Manager/Adapter/认证/检索算法与词典/依赖均未改。

## 实测与限制

60例Legacy→Selective：Precision43.52%→88.89%，Recall98.61%→97.22%，负例误预选9/24→0/24，多工具Full Recall11/12→10/12；heldout各18正/12负/6多，Selective全部覆盖且无误选，已使用不可再称未见。design中代码模块+日程列表中英文两例误选get_calendar_event遗漏list_calendar_events，成本和共享操作词导致语义混淆，未改规则隐藏失败。

同代码核心12例四模式均成功：eager25请求/1461425 Schema字符，progressive_hybrid51/175363，legacy25/176425，selective27/137582；Selective初选漏1个双工具目标，手动补救成功。挑战10例均成功：21/1227597、41/142075、23/158372、23/109693；Selective仍对builtin文件任务误预选MCP代码文件工具，负例正确弃选3/4（Legacy1/4），不能宣称零误选泛化。证据按双下划线取名称末片段，合法远端名含__时会丢失前缀概念而漏选（已独立构造验证）；原排名/手动搜索正常，后续可修正。固定脚本只验证机制，真实模型能力/Token/费用未知。完整分母与规则见phase-18学习文档。

## 归档与验证

实现提交d1808304202d0d1c5d9bdfb7f4d68f6bdaff00a9，唯一annotated phase-18指向该提交；../mybot-mini-snapshots/phase-18.zip共147条目/128文件，SHA256 fed645e2b0175ff7eecfa9fa2a266780885d5926e5e7828103c18ed65f932819。干净APFS worktree的ZIP独立冻结安装/编译/422项及原断言通过；发布ZIP在另一APFS目录再次冻结安装、编译全部mybot/scripts、38项及四模式比较通过。../mybot-mini-learning/phase-18独立restore后冻结安装、编译全部源码、422项及原断言通过；旧检索、旧默认Agent、Phase17三模式、新Routing/Core/Challenge报告除计时/Git元数据外逐字段一致。清理91个确认AppleDouble。CRC/ZIP提交SHA/完整文件清单/无元数据/用户文件已提交版本核对通过；最终记录另作文档提交，不移动Tag。

## 下一步与边界

当前阶段完成，等待用户新任务；不进入19，不自动Push。词法、操作语义和复杂标识符仍会漏选/误选，具体失败与全部分母见phase-18学习文档；固定模型不是自主能力，真实Token/费用未知。不要重新调旧heldout仍声称未见，不修改旧Tag/ZIP，不混入用户修改。历史学习仅保留docs/phases与Git。临时worktree已移除；主工作区只保留用户两文件未提交修改。
