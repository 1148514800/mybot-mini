# C02：双文件 Coding Agent Canary 离线准备

## 学习目标与基线

从 C01 Live 的 c56a03813f9a0472d72d96e5bc3915ff667f0d60 创建独立分支 codex/coding-cross-file-canary-v2。验证两个模块的依赖修复及修订归属；不重新开发 AgentLoop，不修改 C01 成绩、私有账本、原修复、Tag 或 ZIP。本专题没有新编号 Phase，也不进行历史归档。

## Agent 概念与流程

原 create_app → ChatRuntime → AgentLoop → CodingTaskController → ToolRegistry → ProviderFailover → SDK Streaming。模型只提出工具调用，原生 Patch/Receipt、Controller、WebApproval 和 Seatbelt 决定实际执行。模型请求授权和逐命令批准是两种权限。

C02 的 parser 负责精确 CSV/Decimal，report 必须调用 parser，按类别首次出现顺序汇总。只修一模块不能满足独立集成验收。本次 UAT 明确要求两文件实际合法修改，不推广为所有 Coding 修复规则。

## 核心文件与调用

scripts/coding_cross_file_canary_v2/plan.py 固定任务、配置、路径和预算；fixture.py 固定公开六文件 Bug 基线、Reference、Public8/Host18；integrity.py 核对实际文件和累计原生 Journal；server.py 仅在正式运行路径外施加 UAT 白名单与证据门；adapter.py 直接复用 C01 的 SDK/HTTP observer；budget.py 复用原持久 Schema/HTTP/settlement；score.py 复用原 Seatbelt run_suite 和15维评分，增加双文件归属；prepare.py 独立唯一冻结；mock.py 只提供 SDK 合成响应；browser.py 使用既有 OwnedService 与 browser_session。

## 核心原理

每个 Revision 保存两个文件完整 before/after 哈希映射、该次 delta、累计 owned 集合和原生 Journal。一次两文件提交是 Revision1，分别提交是 Revision2。第二次 Journal 可以累计含两文件，delta 只含第二个，不能要求每次 Journal 只有一文件。新修订使旧测试过期。Receipt 一次有效，原文件 SHA 和前后证据不能由模型宣称代替。

完整 Git HEAD/Index/元数据与非允许文件保持不变。未知漂移、Journal 断链和部分发布不确定即 HALT，不 reset/checkout。原生逐文件替换和条件恢复不等于无条件跨文件崩溃原子性。

## 运行环境和命令

macOS、Python3.12+、uv。无需第三方 Fixture 依赖或安装脚本。

```bash
uv sync --frozen
uv run python -m scripts.check_coding_cross_file_canary_v2
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot scripts
node --check mybot/web/static/app.js
git diff --check
```

实际 Chrome 位于本机独立应用路径，使用临时 Playwright 环境 `uv run --no-project --with playwright python -m scripts.coding_cross_file_canary_v2.browser --chrome <Chrome可执行路径> --output <新的私有目录>`。只运行 Mock；默认不连接 Provider。正式新批次 prepare/freeze 已有且不可重复，后续仅 verify。

## 实际案例和结果

Bug Public/Host 均失败，Reference8/18通过。原生双文件一次提交与分次提交分别 verified Revision1/2，独立 Public8/Host18通过。合成审批不是真人；Strict Success 不给 PASS。错误 SHA/Receipt/范围、外部修改、部分发布、链断裂、旧修订测试、拒绝/超时/Stop、预算及断流有独立负向断言。真实 Chrome 双 Profile 隔离、DOM、刷新不重放和正常清理均有证据。最终测试去重数与冻结身份见专题报告 offline-validation/live-readiness。

## 与上阶段变化

C01 只允许 notesearch/search.py；C02 使用全新 csvmini 双模块，独立批次/端口/库，允许双文件累计 Journal。生产代码及 C01 UAT 没有改动。没有第二个循环、额外模型、弱化审批或隐藏测试反馈。

## 常见问题及限制

Controller verified 不是独立业务验收；合成工作流通过不是 Live Strict Success。输入32000估算Token/输出1800预留不绕过，长工具历史仍可能裁剪。模型自由文本和可选 TaskContract 拒绝不自动决定代码正确性；未知来源/需求覆盖仍 UNKNOWN。真实 DeepSeek 跨文件规划、Streaming、用量、真人批准仍待新的 GRANTED_18_REQUESTS 后一次测试。

完整证据、审批边界、安全审计、后续步骤见 ../reports/coding-cross-file-canary-v2/。不运行旧 Case，不继承 C01 剩余2次。

最终离线回归：2205 个去重 unittest ID，其中新增 63，原有 2142；全部通过，源码稳定。独立子进程 Fixture 测试不重复计入总数。

archive-ready: true

## 唯一真实 Live 的独立结果

GRANTED_18_REQUESTS 后，C02 一次执行4/18真实请求，任务/工作流/Strict FAIL。九个只读工具后，第4流约44.968秒调用方取消（首Chunk约43.555秒，228 chunks，无合法终态/EOF），Revision0，无Patch/Receipt/命令或真人审批；原Bug未变，事后独立Public8/Host18均FAIL。固定错误码仍为stream_user_or_caller_cancelled，不改称供应商协议错误；冻结45秒primary窗口是有源码和时序支持的本地超时解释，尚缺明确deadline-owner持久字段。

前三请求真实Usage小计8608输入/313输出/8921总Token；第4缺Usage，全批总数未知，cost=null。所有SDK关闭，自有服务exit0、端口/Lease/数据库/独立Chrome清理通过，344源码冻结postflight通过。唯一Attempt消耗，余14次不用，原Offline PASS不改判成Live PASS，也不重跑。本次Live不是跨文件修复能力的充分样本；新阶段只可另立任务调查超时。详见[独立Live报告](../reports/coding-cross-file-canary-v2/live-results/execution-01/acceptance-report.md)。
