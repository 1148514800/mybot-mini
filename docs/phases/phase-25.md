# Phase25：Coding Agent 可靠性与标准化评测

## 目标与当前检查点

从 Phase24 `ff10fb6` 独立开发。固定 coco2/gpt-6-astra 与 Harness 提交，分三轮执行原12例，每例最多3次独立运行；优先 pagination、serialization、file-recovery。不把历史9/12、多次至少成功一次覆盖或 ability_score 当作本轮首次成功率。

标准Cohort已执行36/36，严格成功15/36。后两轮受到审批值守中断与编排停止边界缺陷混杂，不能作为干净的模型稳定性估计。外部验证及归档结论另见最终验收报告。

## 架构与 Agent 概念

原 AgentLoop 负责 Function Calling 和顺序工具执行，CodingTaskController 负责请求/工具预算、Patch修订与真实测试证据；Git Journal 审计变更归属。Phase25只在它们外层增加持久编排，不替代控制器、不授予权限、不自动重放工具、不改Prompt或Judge。

`mybot/evaluation/coding_campaign.py`：freeze 通过显式白名单冻结模型、Agent配置、Limits、Schema、平台与依赖/评分/Benchmark/私有配置文件哈希，不保存Key或URL；create生成36个独立slot。run_next获取进程锁、检查冻结环境和干净Git，独占创建started，然后复用evaluate单例调用；原评测器每次新建Workspace/Session。原始报告先独占写入并fsync，校验来源，再写finished+SHA。状态不确定、半写入或证据缺失必须人工调查，不能自动安全重试。

`strict_success`要求Agent verified/工作流成功、Judge hidden_pass/repair、公开隐藏通过、真实Patch及测试、正Revision一致、Trace当前修订证据和安全协议通过；允许2/2等合法Revision。

`inventory/summary`验证Run身份与证据SHA，保留失败和未知值。按轮次/案例/难度区分已完成运行成功率、计划完成度、至少一次覆盖；输出资源已知小计、缺失数、线性插值P50/P90/P95，区分Agent与Judge。SHA清单用于发现损坏，不是对可同时改写清单与证据的恶意宿主提供真实性证明。

`evaluate_external_coding.py`复用原Loop、Controller、工具与真实TTY审批，对固定公开python-json-pointer项目增加独立新功能；原测试、公开新增验收测试、修复后独立副本验证。此任务不冒充隐藏Benchmark或生产泛化的充分证据，不运行setup/install脚本。

## macOS / uv 使用

```bash
uv sync --frozen
uv run python -m scripts.check_coding_campaign
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot scripts
# 干净提交后创建离线演练；默认不调用API
uv run python -m scripts.evaluate_coding_campaign init --directory runs/p25-offline --rounds 1 --case-ids pagination-001
uv run python -m scripts.evaluate_coding_campaign run --directory runs/p25-offline
uv run python -m scripts.evaluate_coding_campaign export --directory runs/p25-offline
# Live必须另加 --live --confirm-api-cost，并使用真实TTY和既有逐次命令审批。
```

运行入口支持init/run/status/export，--max-runs默认1、上限36；Live Cohort的init本身不调用API，run才需付费双确认。已完成Run从同一目录恢复会跳过；不确定Run会阻断。跨版本恢复禁止，须保留旧Cohort另建基线。归档副本若无.git，要使用完整克隆或新建明确来源的Git仓库才能初始化冻结Cohort，不能伪造来源。

## 安全与常见问题

原30秒命令上限、真实TTY逐条审批、Seatbelt、SHA/Patch恢复、Revision、Journal、Tool Call ID检查不变。非TTY不能Live。价格缺失时费用null，12次请求不是金额硬上限。相同工具可在不同响应重复调查，不能据此猜测内部推理。审批授予次数未保存在Phase24报告，不能从拒绝数反推审批成功率；Phase25保留null和原因。

## 与Phase24的变化及限制

增加冻结/恢复/统计与独立项目评测入口，既有12例、Reference、Gold、隐藏测试和Judge不变。Phase24历史20次/9例完整成功是跨版本结果；最新error-retry在ff10fb6已真实完整成功。固定版本三轮才支持本轮经验pass@1与best-of-3覆盖，少量合成任务不能证明真实生产项目泛化或对恶意Python候选的形式化隔离。

## Checkpoint B：离线基线

新增24项专项：发现/36槽顺序、重复标识、冻结/漂移、独占写入、成本双门、完成后跳过、中断与执行不确定禁止重放、API失败保留、原始证据丢失/篡改、配置损坏、统计缺失/分位数、Revision2/2与逐项严格成功条件、原生审批未替换及外部公开验收/敏感输出。`uv run python -m scripts.check_coding_campaign`24通过；`uv run python -m scripts.check_phase`25套件940项通过（916+24），Phase1/2原断言和编译通过。日志/tmp/phase25-full.log。原Phase24受封印模块/数据资产、Agent和tools没有变化。

## 标准实测与事后停止边界修复

标准36槽冻结在`b008f35563c266d89ebbdd67a3c31607f9c47819`，模型coco2/gpt-6-astra，原12例及评分SHA不变。Round1 9/12、Round2 6/12、Round3 0/12；Judge隐藏通过31/36，严格完整成功15/36。全部报告保留，不追加标准付费重跑。

审批值守中断时，13个槽位等待输入直至600秒任务超时。原Loop将其记为cancelled/task_timeout，旧编排仅检查execution_uncertain，因而继续后续槽位；未退出的input线程另造成约300秒解释器退出等待。没有向过期审批提示发送yes。13次取消后capsule已关闭，评测归属集合缺失，Journal不匹配累计26文件；原Judge严格拒绝计为修复成功。此问题不能归因于模型代码能力，也不能抹去失败分母。

事后仅修改Phase25外层编排：任何runtime_error、cancelled/execution_uncertain或未完成命令结果均进入必须调查的停止门；每个Live槽位由独立解释器执行，stdin/stdout/stderr原样继承真实TTY。父进程清理期限930秒不增加原API/任务/命令预算，超时或中断发SIGINT，仍不退出则终止子进程并停止，不自动重放。原审批Provider、Seatbelt、Loop、Patch、Journal、Revision、Judge保持不变。该修复不追溯改变旧Cohort，也尚无修复后标准Live验证。

初版冻结工具Schema清单只有8个原生工具；运行时Loop注册另2个Planning工具。原Git提交已固定实际10工具代码，事后离线补充清单与请求Schema字符数一致，并明确标注补录时间。V2在freeze时注册Loop，预先记录完整10工具及temperature=0.1、max_retries=0。

新增8项离线回归覆盖取消审批等待停止、未完成命令屏障、失败分类不伪造Journal错误、完整工具冻结、子进程继承终端、超时中断与终止不重放以及真实内核PTY证明。原24项保留，专项共32项；全量25套件948项（原916+新增32）全部通过，Python编译通过；日志/tmp/phase25-full-v2.log。
