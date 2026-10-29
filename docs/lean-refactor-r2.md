# Lean Refactor R2：实质性精简与工程减负

## 基线、范围和结论

基线 `codex/lean-core-refactor-v1` / `d262049b1403c8873cd5b5036fd1628d044bd7d4`，交付分支 `codex/lean-project-refactor-v2`。最终 SHA 见交付消息，或 `git log -1 --format=%H -- docs/lean-refactor-r2.md`。

本轮没有重复 R1 的 AgentLoop 拆分，没有移动生产模块。找到三个可证明的小范围简化点，生产代码净减少 **11 行**，Python 文件仍为 **109 个**。这是有限删减，不是全面架构瘦身。主要工程收益另来自约 20 秒的核心测试入口，以及不改历史的精简工作区方式。

开发使用独立 APFS 工作树，原 main 的 app.py 与 workspace/instructions/USER.md 未提交修改没有携入或覆盖。本轮不是 Phase；不创建或改动 Tag/ZIP，不启动真实模型、Canary、付费 UAT 或浏览器 UAT。

## 审计依据与保留决定

检查了实际源码、导入和调用、既有测试/子类、历史脚本入口，并使用 R1 原始实现作离线差分验证。静态搜索只是寻找候选，不作为删除依据。

| 范围 | 审计结论与处理 |
| --- | --- |
| agent/context_manager.py | 字符预算与 Token 预算共用同一套 canonical 边界、完整轮次验证、current/system/pin/lifecycle 复制及计划投影；合并这部分。两种预算算法、错误文本、裁剪与摘要策略仍不同，保留。 |
| agent/token_counter.py | Measurement 仅在 measure 内构造并立即 asdict，调用方只接收 dict；无注册、动态选择或持久化入口。直接生成同字段、同顺序的字典，删除中间记录类型及转换。TokenCounter 对外方法保留。 |
| tools/base.py | to_text 在失败时必先添加非空错误文本，因此最终空 parts 的失败回退不可达。删除重复回退，不删除任何错误输出。 |
| AgentLoop/R1 转发接口 | Evaluation 子类会重写 _finish_turn、_route_initial_tools；历史测试会替换 _execute_tool。没有把这些入口当死代码删除，也没有再拆模块。 |
| config.py / ToolRegistry | 配置与 Registry 可被分别直接构造，各自处于输入边界；重复模样的校验不能证明冗余，保留。Web launch 兼容/严格模式差异不变。 |
| storage/ | Session 深复制负责隔离调用者修改；JSON 与 EventStore 是不同可选后端，恢复投影也不是执行状态副本。全部保留，数据格式不变。 |
| web/ | requests/tokens/usage_known 在没有资源快照时仍有兼容回退语义，不能直接替换为 resources 字段。审批、关闭、WorkspaceLease、历史终态落盘顺序保留。 |
| tools/审批/隐私 | Command/File/Undo/MCP 请求与结果语义不同；Web、存储、Evaluation 脱敏规则和上限不同，不合并为宽松通用函数。Patch/Receipt、RunCommand/Seatbelt 安全实现未改。 |
| evaluation/及历史 Operator | 24 个模块已位于运行时依赖闭包之外；仍被检查、复现和历史审计使用。_primary 等兼容引用也仍被 smoke/UAT 入口使用，没有仅凭正常运行不访问而删除。评分、冻结证据、Fixture/Gold、账本全部不改。 |

## 真正删减，与结构移动的区别

1. `_current_context` 是 ContextManager 内一个私有 helper，供两个既有预算入口调用。重复实现合并为一份，但每次原有校验仍执行；没有缓存可变状态或跳过边界检查。由于保留两个策略和可读格式，这部分仅净少 1 行。
2. TokenCounter 删除每次请求测量时临时创建 Measurement 并递归 asdict 的转换，净少 8 行。JSON 序列化参数、UTF-8 计量、framing margin、None/accuracy 字段与 NaN 拒绝不变。仓库内不存在 Measurement 的其他消费者；不承诺仓库外直接导入这个原实现细节的私有集成兼容。
3. ToolResult 删除不可达的第二份失败文本回退，净少 2 行。失败、成功、空输出、metadata 的行为按 R1 原实现比较。

生产 diff 为 **+20 / -31，净 -11**；总行数 **14,063 → 14,052**，文件 **109 → 109**。没有删除注释来凑数，没有代码压行，没有新增生产模块、服务类或框架。测试与说明新增行另计，不伪装成生产删减。完整交付 diff：新增288行 / 删除46行，净新增242行（含文档与测试）。

## 运行时与实验层

新进程中实际导入的项目模块数量（含 package 节点，排除第三方）前后完全相同：

| 入口 | R1 | R2 | 主要依赖 |
| --- | ---: | ---: | --- |
| import mybot.main | 43 | 43 | package lazy run_gateway → app → AgentLoop/ContextBuilder、config、ToolRegistry、MCP、Provider、Skills、SessionStore |
| import mybot.web.__main__ | 4 | 4 | mybot、web、__main__、launch；诊断前不加载 runtime/client |
| import mybot.web.server | 54 | 54 | server → ChatRuntime → 同一 AgentLoop/Provider/MCP/工具；另含 WebApproval、WorkspaceLease、EventStore/projections |

包括函数体内和可选分支的保守静态 import 闭包共 70 个 mybot 模块，没有 mybot.evaluation 或 scripts。新增回归在新进程的 import finder 中主动拒绝这两个 namespace，再导入上述三个入口并构造默认 GatewayConfig，成功通过。实际启动与请求行为另由现有 CLI/Web/Mock 测试覆盖；这里不通过导入启动真实客户端请求。

实验层方向是 Evaluation/脚本依赖运行时，不是运行时依赖实验层。因此没有为目录外观迁移文件。可复查：

```bash
uv run python -X importtime -c 'import mybot.main'
uv run python -X importtime -c 'import mybot.web.server'
uv run python -m scripts.check_lean_refactor
```

## 核心开发检查与完整检查

新增 `scripts/check_core.py` 仅用标准库 unittest 加载既有完整套件，没有复制测试逻辑、方法级白名单或新测试框架：Session/AgentLoop、Provider Chain、Tool Authority、Patch Preview/Receipt、SessionEventStore、Web UI/Runtime、Model Streaming、R1/R2 回归。缺失模块或断言失败仍返回非零退出码。

```bash
uv sync --frozen
uv run python -m scripts.check_core
# 仍然保留原来的全部验证，默认文件与调用顺序未改：
uv run python -m scripts.check_phase
```

核心入口实测 **221 项通过，17.73 秒**；独立 sparse clone 中 **221 项通过，20.44 秒**（sparse测试期间完整回归也在运行，不用于严格性能对照）。这两者覆盖面小于完整入口，不宣称原完整回归加速。更聚焦的工作仍可直接用 `uv run python -m unittest scripts.check_session` 等现有命令。

新增 `check_lean_refactor` 的 4 项检查包括：180 组确定性上下文差分（字符/estimate/strict、启用/禁用、不同预算、成对/非法工具消息、历史、Pin/lifecycle、计划），比较完整结果、异常类型/文本和输入未被修改；Token 计量字典及拒绝行为；ToolResult 24 组组合；运行时导入边界。固定 R1 SHA 通过 git show 读取，不下载、不复制基线测试，也不改旧源码。需要保留 Git 历史，不能使用丢失该提交的浅克隆。

完整回归结果：原 `uv run python -m scripts.check_phase` **60组1739项、60个OK、零失败/零跳过，退出码0；360.72秒**。R1记录为354.28秒，本轮没有宣称全量加速。

专项 context/token/context_compaction/tool_authority **76 项通过**。Python compileall、两份 Web JS 语法、Git diff 检查结果：全部通过。旧测试、断言、默认完整入口均未修改。

## 历史报告依赖与非破坏性精简工作区

基线 docs/reports 有 **1111 个已跟踪文件，16,665,356 字节（约 15.9 MiB）**。在基线 1671 个已跟踪文件中隐藏这些文件后，工作区只需展开 560 个；R2 新增源文件/说明会正常展开。只减少工作区可见文件，不缩减完整 .git 历史、网络下载量或对象库体积。

正常运行时没有历史报告依赖。源码中明确的历史读取入口是：

- `scripts.check_tool_verification_reliability --reanalyze` 读取 request-budget-full-batch/evidence 下 raw.json；默认 unittest 入口不执行 reanalyze_history。
- `scripts.audit_phase25r` 默认读取 docs/reports/phase-25。

其他回归中的临时 reports 目录在 TemporaryDirectory 中生成，不是 docs/reports。独立 sparse clone 已实际验证核心检查和导入边界；完整回归在完整开发工作树验证，没有把这个结果冒充 sparse 全量验证。运行历史重分析前必须恢复报告，否则可能得到空材料或缺失文件错误。

建议只在**新的独立克隆目录**执行，以下不操作已有 main 工作树；目标路径应不存在：

```bash
git clone --no-checkout --branch codex/lean-project-refactor-v2 \
  https://github.com/1148514800/mybot-mini.git "$HOME/mybot-mini-lean-r2"
cd "$HOME/mybot-mini-lean-r2"
git sparse-checkout set --no-cone '/*' '!/docs/reports/'
git checkout codex/lean-project-refactor-v2
uv sync --frozen
uv run python -m scripts.check_core
```

没有使用 --depth，既有固定 SHA 回归仍能访问历史。验证采用 `--no-local` 创建独立 APFS clone，检查所有被隐藏路径都属于 docs/reports，并通过 git object/hash 对照证明报告保留；没有对用户 main 设置 sparse-checkout。验证候选代码来自当前工作树明确列出的三个生产文件与两个检查脚本，不复制真实配置/凭证/Session。

需要历史报告或完整文档时，在该**独立克隆**中运行 `git sparse-checkout disable` 恢复全部已跟踪文件；只查看历史对象可用 `git show HEAD:docs/reports/<具体路径>`。这些操作不删除提交，不改写报告，不改 Tag/ZIP。已有配置、虚拟环境、会话数据等未跟踪文件不会因 sparse 变成可提交材料。

## 同环境 Mock 性能

在完整回归结束、没有并发测试时，使用同一虚拟环境 Python，依次在干净的 R1 工作树与 R2 工作树运行同一个计量脚本；两者均无真实 config.json。导入为各11个新子进程的中位数，只计 import，不计进程/uv启动。

| 指标 | R1 | R2 |
| --- | ---: | ---: |
| import mybot.agent.loop 中位数 ms | 172.383 | 171.634 |
| import mybot.app 中位数 ms | 341.592 | 342.260 |
| import mybot.web.runtime 中位数 ms | 346.777 | 351.548 |
| import mybot.config 中位数 ms | 150.944 | 151.872 |
| Mock请求中位数 ms | 0.4615 | 0.4660 |
| Mock请求最小–最大 ms | 0.4162–0.8075 | 0.4324–0.8231 |

Mock请求中位数约+0.96%，导入变化约-0.43%～+1.38%；样本范围重叠、量级相同，不声称此次精简带来可确认的提速。

计量复用原 `scripts.measure_core_refactor`，CPython 3.12.14、相同 uv.lock、macOS 26.6.2 arm64、APFS；固定 offline done 响应，预热 10 轮后测 200 轮、内存 Session，每轮断言 1 次物理 Mock 请求。真实模型请求 0，未测模型质量、外网延迟或付费能力。

## 未改变和限制

保留多 Provider、Streaming 终态/取消、CodingTaskController、Patch Preview/Receipt、RunCommand/WebApproval/Seatbelt、WorkspaceLease、Session/EventStore、MCP 与 Skills。R1 转发与现有安全回调仍然保留；更深的状态合并没有充分等价证据，本轮不做。

净删减仅 11 行，不能宣称项目已经大幅变小；生产模块数和导入链没有下降。新增测试/说明有维护成本，但快速入口只维护套件名称；差分测试专门约束本轮变更。共享 ExFAT Git 的 AppleDouble index 警告仍存在，没有修改其共享元数据；APFS 工作区和独立 clone 没有新增这种归档内容。没有真实 API/Canary/历史重评分结果，也没有更改历史结论。
