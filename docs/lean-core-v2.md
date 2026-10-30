# Lean Core v2：核心收敛与兼容层退役

基线 `bb4a5f4311f4e98936e0bd206986ccbdb00ee4b3`，工作分支 `codex/lean-core-v2`。
本轮为产品合同变更，不是新的 Phase；不创建 Tag、ZIP、Canary 或真实模型证据。

## 新合同与明确不兼容项

- Runtime 仍是同一 AgentLoop、ContextManager、任务状态和生命周期；CLI/Web 共用。
- Models 保留 Provider 顺序、任务内黏性、新任务重置、唯一 Failover 门组合、Streaming 终态/取消、Usage 和物理请求预算。
- Tools 保留只读仓库工具、Repo Map、Planning、原生 Patch/Receipt、Journal/Revision、命令审批和 Seatbelt。删除 WriteFileTool、旧文件审批模块、Registry 的 legacy_confirm 分支及权限分类。过期工具调用固定 `TOOL_RETIRED_WRITE_FILE`，包括直接调用 Registry、伪注册同名工具和畸形参数，不重写成 Patch。
- Storage 默认 memory，仅可显式选择 event_sqlite。移除 SessionStore 的 JSON load/save/clear 运行后端及 AgentLoop 双重持久化。保留严格完整轮次校验器，供正常内存协议与独立迁移读取使用。
- 删除模块级配置正文/Provider 状态及导入时读文件。`read_config` → `config_from_document` → GatewayConfig 是显式合同；CLI、Web、check 共用。GatewayConfig 直接构造保留，默认值纯粹、不会读取真实配置。`--workspace` 只覆盖本进程。
- MCP/Skills 关闭时不导入/构造 manager、transport、SkillRegistry；公共配置校验和权限分类仍会导入部分轻量 MCP 模块。开启时 enter/call/exit 仍在 owning task，未引入全能工厂。
- Evaluation/scripts 不进入正常运行导入链。旧 Operator 的配置调用改为显式快照/加载；历史报告、评分、Fixture 数据、Gold、账本及冻结证据不改。

不再接受 `coding.file_access`（包括 read_only）、`session.persist`（包括 false）、`session.path`、`session.backend=legacy_json`、`context.token_budget.mode=legacy_chars`。旧 GatewayConfig 关键字同样不兼容，不能依赖全局 `_CONFIG` / `_PROVIDERS` 打补丁；使用显式构造、`providers` 快照或 `config_from_document`。

## Token 预算

默认 `estimate`、`input_limit=16000`，一个 UTF-8 字节对应一个估算 Token，再加明确的 framing/隐藏开销余量。这是保守启发式，**不是经验证的精确 Tokenizer 或计费 Token 数**。字符数、UTF-8 字节、估算输入、供应商报告 Usage 分开显示。

`context.enabled` 仅控制裁剪/压缩，关闭也计量并拒绝超额请求。配置的 Provider 模型窗口还会扣除输出预留，不增加额度。`strict` 在部署 Tokenizer/窗口无法验证时拒绝发送。`max_chars` 不再参与请求额度；工具结果及摘要的字符裁剪上限仍有独立意义。

含大型工具 Schema 的旧任务可能在默认 16000 额度下停止；应由用户依据需求显式设置 input_limit，不能把关闭 context 当作无预算运行。测试中的大 Schema 合成场景显式声明自己的输入额度，模型请求次数预算和失败门保持原断言。

## 配置迁移（与数据迁移分开）

只操作用户指定的文件，本轮仅使用临时合成配置测试，未修改真实 `config/config.json`。

```bash
uv run python -m scripts.migrate_config_v2 --config /absolute/config.json --dry-run
# 仅当理解字符预算到 UTF-8 保守估算的差异后：
uv run python -m scripts.migrate_config_v2 --config /absolute/config.json --confirm-token-estimate --apply
```

默认只读。移除 file_access 后普通文件访问只读，不自动开启任何写入/命令能力；legacy_chars 转换必须确认，input_limit 原值保持。只有明确 persist=false 的闲置 JSON 设置可删除；启用中的 JSON 配置会以 `SESSION_DATA_MIGRATION_REQUIRED_NO_AUTOMATIC_BACKEND_CHANGE` 停止，不能猜测用户需要 memory。

完整新配置校验成功后，创建独占 `config.json.v1-backup`（0600），再原子替换为受限权限的新文件。已有备份不覆盖；失败保留原配置。输出只含固定错误/变更类别，不输出 API Key、完整 URL 或配置正文。`--check` 对旧字段给出迁移错误及命令建议，不构造模型 Client。

## JSON Session 数据迁移

先创建 workspace 之外的私有目标目录（0700）。必须显式给 workspace 和 CLI/Web channel，确保使用与 Runtime 相同的 workspace 哈希命名空间。目标数据库必须不存在；已有 DB 及其 sidecar 不打开、不覆盖。

```bash
uv run python -m scripts.migrate_legacy_session \
  --source /absolute/old-session.json \
  --destination /absolute/private/events.sqlite3 \
  --workspace /absolute/project --channel cli --dry-run
# 检查预览后，再使用相同参数加 --apply（移除 --dry-run）。
```

严格校验 version=1、完整轮次、角色、工具配对、重复 JSON key、文件大小。源文件永不删除/覆盖。候选数据库在独立临时私有目录构建，逐条核对数量、顺序、文本，并重新打开执行 EventStore 完整性/事件提交/投影校验；通过后才独占发布目标文件。失败不修改已有目标 DB。

普通 user/final assistant 历史可以无损迁移。隐私脱敏或文本大小规则会改变内容时，返回 `TEXT_NOT_LOSSLESSLY_REPRESENTABLE`，不声称完整等价。迁移不导入工具授权、Receipt、verified、Controller 或可执行状态。Runtime 恢复文本时仍添加原有非执行证据提示。

含 tool_calls/tool 的历史默认 `UNSUPPORTED_TOOL_HISTORY`。可选 `--flatten-tool-history --confirm-lossy --apply` 明确选择有损模式：保留用户及助手文本（中间助手段落用迁移标记连接），省略工具调用参数和工具结果，报告工具交互省略数，并先创建源文件旁 0600 的独占 `.migration-backup`。此模式改变消息数量/结构，**不等价于原始历史**；原文件和备份均保留。

只有迁移及验证成功后，用户才可手动删除配置中的 persist/path，显式设置 backend=event_sqlite 和 event_path；这一步不会由任一工具自动执行。

## 测试合同迁移

旧 JSON 持久化测试场景改为迁移与 SQLite 恢复、失败保全、权限、隔离及不恢复执行状态的断言，保留原场景名称并新增迁移覆盖。
旧写入成功场景：协议/Planning 测试改用真实只读工具验证配对和证据；Authority 测试明确断言固定拒绝与零副作用；原生 Patch 专项继续验证真实修改和 Receipt。
旧评测数据中的 write_file 不改输入/Gold，当前运行必须失败，停止后的物理请求和 Usage 反映实际发送次数。历史文档诊断仍直接验证原评分函数，不调整历史评分算法。
旧 `_CONFIG`/`_PROVIDERS` 测试迁移到显式配置对象/解析入口；字符预算边界测试改用实际 TokenCounter 请求视图，保留拒绝、裁剪、Schema 和协议完整性断言。取消测试的同步等待增加有界超时，避免前置失败后无限等待，不跳过断言。

补充测试映射：`check_persistence` 原16个场景名称保留，但 JSON 自动保存/恢复、fsync/replace、clear 和窗口语义正式替换为独立迁移与 SQLite 合同；Agent 失败回滚、步骤上限、完整工具配对继续由 Session、EventStore 和 Runtime 专项覆盖。`check_web_ui.test_no_session_disk_even_cli_persist` 更名为 `test_memory_session_creates_no_legacy_disk`，断言新 memory 后端不创建旧文件。`check_tool_agent_eval` 的 Schema 字符数及 MCP 工具数量按删除 write_file 后的实际值更新；原数据集和评分函数没有改变。差分回归保留180组，改为 estimate/strict 两种现行模式，legacy_chars 拒绝由新专项单独覆盖。

## 度量与最终验收

生产 Python（包含 mybot/evaluation，统计口径与 R2 相同）：**109 → 108 个文件，14,052 → 13,834 行；+305 / -523，净减少218行**。删除一个旧审批模块，没有新增生产模块。新增迁移脚本与回归属于 scripts，单独计入完整 diff，不伪装成生产删减。

删除3类运行路径：旧直接文件写入、JSON 双持久化、字符预算旁路；退役3个字段（file_access、persist、path）和2个枚举值（legacy_json、legacy_chars）。另删除导入时配置正文与 Provider 全局状态。Provider 顺序/字段规则从多处实现收敛为 config 中的一份；直接构造 GatewayConfig 后建立客户端时仍保留边界验证，不能用“去重复”绕过它。

CLI/Web/check 都用同一 config_from_document；CLI/Web 保留2个宿主初始化入口和各自审批/资源所有权，ToolRegistry 的配置映射仍只有1处。没有创建第二个 AgentLoop 或生命周期工厂。

新进程实际导入数量（含 package，排除第三方）：

| 入口 | 基线项目模块 | v2项目模块 | MCP/Skills 基线 → v2 |
| --- | ---: | ---: | ---: |
| mybot.main | 43 | 36 | 15 → 9 |
| mybot.web.__main__ | 4 | 5 | 0 → 0 |
| mybot.web.server | 54 | 47 | 15 → 9 |

Web 命令入口多出的1个是无副作用的 config 合同模块。默认 Agent 初始化的禁用扩展边界回归拒绝导入 manager/transport/SkillRegistry，验证通过；所有入口均无 Evaluation。保留轻量 MCP 权限/配置模块有实际调用关系，不为了数字移除。

历史合成对照的适配：请求效率、Failover Batch 和 A/B 协议专项现在显式注入离线 Provider 与160000输入额度，双方使用同一额度，原模型请求次数上限不变。工具验证对照只从固定 SHA 提取实际参与比较的原 `_execute_tool` 方法 AST，不执行已退役的 JSON 后端导入；冻结方法正文、Patch/Controller 对照及所有成功/失败断言保持。未执行 Live A/B 或付费 Judge。

剩余兼容性风险：旧配置/私有构造关键字必须迁移；大型 Schema 可能在默认16000下被拒绝；strict 暂无精确 Tokenizer 映射；工具历史只能显式有损迁移，隐私规则改变文本时拒绝迁移；迁移仅支持新数据库，不合并已有历史。真实 Provider 和历史 Operator 没有做 Live 验收。共享 ExFAT Git 的 AppleDouble index 警告仍存在，本轮不修共享元数据。原 main 工作树及其未提交文件不改。

### 最终离线验收

- `uv run python -m scripts.check_phase`：**61组1752项，1752通过，61个OK，0失败/0跳过，退出码0，354.89秒**。另含入口中的 debug/无debug工具协议 smoke 与 list_files 检查。基线 R2 的已有验收记录是60组1739项、360.72秒；不是本轮重测基线全量。新增13项产品合同补充覆盖，没有减少原完整套件。
- `uv run python -m scripts.check_core`：**234/234通过，退出码0，17.90秒**（unittest主体17.197秒）。R2既有221项17.73秒；不把覆盖面不同的核心入口冒充全量加速。
- `uv run python -m unittest scripts.check_project_launch scripts.check_repo_map scripts.check_lean_core_v2`：**56/56通过，4.57秒**，其中迁移/退役专项13项。这里与核心/全量有重叠，不累加为独立测试总数。
- `uv run python -m compileall -q mybot scripts`、两份 Web JS 的 `node --check`、`git diff --check` 全部通过。
- 最终全量前的探索性运行曾暴露旧配置注入、工具数量/Schema字符数、冻结方法导入和合成输入额度问题；均修复后重跑完整入口。一次局部 Batch 运行期间编辑文件触发环境指纹拒绝，随后冻结文件、完整复跑通过；没有放宽该保护。
- 真实模型请求 **0**；所有模型均为合成响应或 SDK MockTransport。没有 Canary、Live Benchmark、真实浏览器 UAT、付费 Judge；历史评分/报告/Fixture数据/Gold/账本/Tag/ZIP无改动。

### 同环境性能对比

macOS 26.6.2 arm64、Python3.12.14；使用当前同一虚拟环境，先干净 R2 worktree，再 v2 worktree，串行运行 `scripts.measure_core_refactor`，无并发回归。每个 import 为11个新进程样本，表列中位数，不含进程/uv启动；Mock为相同 hello/offline done、每次新会话、1个物理合成请求，预热10次后200次中位数。脚本只将退役的 session_persist=False 改为显式 memory，不访问 API。

| 测量 | R2 | Lean Core v2 |
| --- | ---: | ---: |
| import mybot.agent.loop | 168.010 ms | 163.174 ms |
| import mybot.app | 332.019 ms | 165.292 ms |
| import mybot.web.runtime | 338.653 ms | 168.991 ms |
| import mybot.config | 146.849 ms | 7.759 ms |
| 简单Mock请求 | 0.439 ms | 0.468 ms |
| AgentLoop行数 | 361 | 357 |

CLI/Web Runtime导入约减半，config导入减少约94.7%，来自去除导入时配置/SDK和禁用扩展的初始化路径。Mock请求中位数增加约6.8%（0.030ms）；基线关闭context走旧字符旁路，v2始终计量，两者产品预算合同有意不同，不宣称请求速度提升。样本区间分别0.410–0.760ms和0.432–0.509ms，不能据单次微基准推断总体吞吐量。

完整交付diff（含测试、迁移脚本和文档）：109个文件，+1411 / -1210，净新增201行。生产净删减与迁移/测试的维护成本分开报告。

### 交付标识

Implementation/Acceptance 使用同一提交：本文件所在的 Lean Core v2 交付提交（`git rev-parse HEAD`），分支 `codex/lean-core-v2`。最终交付消息报告完整SHA，并在Push后核对远程同名分支HEAD。无需也没有合并main；原main仍在 `8c1a049904f9544fc5eaeb53c06f6712e43ea320`，保留原 `mybot/app.py` 和 `workspace/instructions/USER.md` 未提交修改。
