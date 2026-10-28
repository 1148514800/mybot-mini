# Core Refactor R1：精简 Agent 运行时

## 范围与基线

- 基线：`codex/repo-map-scoped-v2` / `1b5af3543dde6bde51c3863a6d88b3c40ab8d778`。
- 交付分支：`codex/lean-core-refactor-v1`；最终 SHA 见交付消息，或执行 `git log -1 --format=%H -- docs/core-refactor-r1.md`。
- 从指定 SHA 创建干净 APFS 工作树。用户原目录在 main，已有 app.py 与 USER.md 修改，未携入本分支，也未更改。
- 本轮不是 Phase，不创建或覆盖 Tag、ZIP；不更新历史 Benchmark、Fixture、Gold、评分、账本、冻结证据或 C01/C02 结论。真实模型请求 0。

## 原实现的问题与实际删除

AgentLoop 同时负责循环、上下文压缩、工具批次、事件投影、会话控制、持久化与任务清理。修改工具事件需要阅读整个循环，异常清理和预算边界不易定位。

可证明的重复已经删除：

1. CLI/Web 各自覆盖 `before_fallback`，而 AgentLoop 已经组合宿主门和 Controller 门。删除两个宿主端重新赋值，保留唯一组合点；这同时修复宿主拒绝回调被覆盖的问题。
2. CLI/Web 各复制一份 config → ToolRegistry 的参数映射，改为现有 registry 模块内的 `build_configured_tool_registry`。两个宿主仍显式传入自己的文件与命令审批对象。
3. 工具批次的 `before_batch/state` 与 `before_tool` 拒绝路径返回同一 `autonomy_stopped` 结果，合并为短路条件；先检查批次和状态，只有允许时才调用 `before_tool`。
4. ToolRegistry 已将非 ToolResult 返回转换为错误结果，observer.complete 后再次检查相同类型的分支已删除；异常转换、授权检查和 observer 的顺序不变。
5. session/context/skills 三个完全相同的配置取值和对象检查合并为 `_section_value`，旧名称通过标准库 partial 保留，错误文本、缺省值与调用方式不变。

## 职责与调用关系

```text
CLI run_gateway / Web ChatRuntime._run
  ├─ build_configured_tool_registry(config, 各自审批)
  ├─ MCPClientManager enter（宿主 owning task）
  ├─ 既有 build_gateway_client / 注入 Mock factory
  └─ 唯一 AgentLoop
      ├─ turn_lifecycle.handle_message / _run_message
      │   └─ AgentLoop._handle_message：步骤循环、模型调度、停止决策
      │       ├─ context_preparation：请求视图、压缩、统计、工具预选
      │       ├─ AgentLoop._request_model：请求事件、Streaming observer、计费
      │       └─ tool_dispatch.dispatch_batch：参数解析、执行、结果与安全投影
      └─ turn_lifecycle：结束报告、Session 保存、receipt/guard/journal 清理
  └─ 宿主 MCP exit、client close、history/lease 清理
```

新增三个有实际实现的函数模块，不新增服务类、工厂类、第二个 AgentLoop 或状态副本。状态仍由 AgentLoop 持有；转发方法保留既有测试、Evaluation 子类及 monkeypatch 调用入口。14 个提取函数（含 safe_read_metadata）的 AST 与基线一致。`safe_read_metadata` 仍从 loop.py 可导入。

修改生产模块：`agent/loop.py`、三个上述模块、`app.py`、`web/runtime.py`、`tools/registry.py`、`config.py`。ProviderFailoverClient、Session/EventStore、CodingTaskController 和原安全工具实现未改。

## Failover 所有权和安全边界

AgentLoop 构造时捕获已有宿主 `before_fallback`，并绑定 `host_gate(definitions) and controller.before_request(definitions)`；无 Controller 时只检查宿主门。宿主门先执行，拒绝或异常均不能进入备用请求。CLI/Web 不再覆盖该组合回调。宿主应在构造 AgentLoop 之前设置自己的门；运行中的任意外部重新赋值不属于本轮提供的新接口。

ProviderFailoverClient 仍负责顺序、按任务保持当前 Provider、新任务 reset、每次物理 dispatch、超时、流终态/关闭确认和凭证集合。Controller 每次备用请求至多检查一次；预算 2 的用例恰好发送 2 次，第 3 个 Provider 不构造。主请求、压缩保留预算、宿主 dispatch 授权和 TokenCounter 检查全部保留。

原生工具类型判定、权限拒绝后停止批次、命令审批与 Seatbelt、Patch 发布/恢复、Receipt 生命周期和历史脱敏、Session 事件格式、Streaming 终态与清理规则不变。远程或伪装工具不能发布原生读取路径、Patch diff 或安全错误字段。

## 有意保留的差异

- MCP enter/call/exit 继续在 CLI/Web 各自 owning task；未引入跨 task 的统一资源工厂。
- CLI 进程循环与 Web 按任务执行的超时、审批、关闭和历史落盘时机不同，不统一 finally。Web 仍等资源关闭确认后持久化终态并释放 lease。
- Provider 构造原本已共享 build_gateway_client；AgentLoop 构造包含 Web 专属 Session、history、steer 与事件参数，不为几行调用增加另一层工厂。
- web/launch.py 已复用 provider_order/validate_provider，但其严格 JSON、URL、workspace/Git 预检与 config.py 的兼容加载语义不同；保持差异，不扩大本轮到配置格式迁移。`--workspace`、`--check`、Provider 顺序和本地脱敏不变。
- CLI/Web 运行方式未变化，因此 README 无需修改运行命令。
- Evaluation/scripts 的历史材料不迁移。以后可在独立任务中为离线入口建立索引，但不能用新结果替换历史证据。

## 计量方法与结果

2026-10-28，在同一台 macOS 26.6.2 arm64、CPython 3.12.14、同一个 uv 虚拟环境/uv.lock 依赖下测量。原始 SHA 使用 git archive 解到 APFS 临时目录；重构版也在 APFS。两版没有真实 config.json，使用同一份 `scripts/measure_core_refactor.py`，依次运行，期间没有并发测试。

行数为 mybot/ 下全部 Python 文件的物理行数（包含注释、空行及现有 evaluation 模块，不包含 scripts/docs）。Git 增删行包含搬移，不能解释为删除了同等数量的逻辑。

| 指标 | 基线 | R1 | 变化 |
| --- | ---: | ---: | ---: |
| mybot/ Python 文件 | 106 | 109 | +3 |
| mybot/ Python 总行数 | 13,989 | 14,063 | +74（+0.53%） |
| agent/loop.py 行数 | 844 | 361 | -483 |
| 生产 diff 新增 / 删除 | — | +620 / -546 | 净 +74 |
| 全部交付 diff（含文档/测试） | — | +960 / -561 | 搬移行包含在内 |
| CLI/Web 复制的 config → registry 映射位置 | 2 | 1 | 共用现有 registry 模块 |
| failover 回调组合/覆盖位置 | 3 | 1 | AgentLoop 唯一组合 |
| MCP / Provider / Agent 宿主组装调用位置 | 各 2 | 各 2 | 保留宿主生命周期差异 |

导入时间：每模块 11 个全新 Python 子进程，计时只覆盖 import，不包含进程创建或 uv 启动；表中为中位数与最小–最大值，单位 ms。请求时间：内存 Session、临时空工作区、固定 `offline done` Mock 回复、每轮清空模型 Session，预热 10 轮后测 200 轮 handle_message；每轮断言恰好 1 次物理请求，无工具执行、无 SDK 网络请求。不代表冷启动完整 CLI、磁盘持久化或实际模型延迟。

| 指标 | 基线 ms（范围） | R1 ms（范围） |
| --- | --- | --- |
| import mybot.agent.loop | 169.308（166.839–216.159） | 169.756（168.763–172.335） |
| import mybot.app | 337.246（334.279–341.421） | 338.018（334.051–344.456） |
| import mybot.web.runtime | 347.311（341.644–350.448） | 344.121（340.205–349.018） |
| import mybot.config | 149.098（146.780–150.416） | 149.095（147.028–151.075） |
| 单次离线 Agent 请求 | 0.4671（0.4181–0.7945） | 0.4550（0.4162–0.8093） |

导入中位数变化约 -0.92%～+0.26%，简单请求约 -2.60%；均不能据此声称显著加速。这里没有观测到明显性能退化。总行数略增，整体精简收益有限；明确收益是删除重复回调/映射/分支，以及缩小循环的阅读范围，不能把搬家当作整体复杂度下降。

复测：`uv sync --frozen` 后运行 `uv run python -m scripts.measure_core_refactor`。复测旧 SHA 时将同一计量脚本复制到独立旧代码目录，并使用同一虚拟环境 Python。

## 离线验证

最终 `/usr/bin/time -p uv run python -m scripts.check_phase` 退出码 0：**60 组 unittest、1739 项，60 个 OK，零失败、零跳过，real 354.28 秒**；入口自带循环/日志/文件路径检查也完成。此前中途失败的两次执行不算完整通过。

| 实际执行 | 结果 |
| --- | --- |
| Session、Provider Chain、Tool Authority、Patch diagnostics、Web UI、Project launch、Autonomous Coding、Receipt、Streaming failover/model、Git workflow 专项 | 436 项通过 |
| stream_shutdown、stream_sse_lifecycle、stream_protocol_diagnostics、stream_legacy_function 补充 | 92 项通过 |
| 新增 check_core_refactor（含 CLI/Web/直接 Mock 的 9 个子场景、事件身份和配置验证） | 5 项通过；已接入完整入口 |
| 基线兼容修正专项 | Campaign 33 项、failover smoke 13 项通过 |
| 完整入口后半段预检 | 32 组718项通过；随后仍从头跑完整入口 |
| Python 编译 | `uv run python -m compileall -q mybot` 及本轮新增/修改脚本通过 |
| JS 语法 | `node --check mybot/web/static/app.js` 和 `markdown.js` 通过 |
| Git | `git diff --check`、staged diff 检查通过；只提交本轮文件 |

专项与全量有重叠，不能相加宣称独立用例总数。源码与提交内容审查未发现真实凭证；跟踪路径检查无真实 config.json、.env、.venv、Session 数据库/历史、._ 文件、ZIP 或超过 5 MiB 文件，补充高置信度密钥特征检查无候选；这些自动检查不替代对本轮 diff 的人工审查。

测试维护包含三类兼容调整，没有删除旧测试或放宽断言：

- Patch 诊断的静态类型门断言改为读取 tool_dispatch.py，断言内容不变，并新增非原生工具伪造事件元数据的行为检查。
- 首次完整回归在 Campaign 的旧“10 个工具”断言停止。在指定原始 SHA 的独立目录执行同一用例，也得到 `11 != 10`。基线已经注册 repo_map，因此改为 assertCountEqual 锁定完整 11 项名称及重复数量，保留规划工具与采样断言；专项 33 项通过。没有修改 freeze 实现、Benchmark、历史冻结证据或评分。随后重新执行完整入口。
- 第二次全量运行暴露旧 smoke 测试配置缺少 GatewayConfig 字段；原始 SHA 同样在 setUp 失败。测试改用带合成凭证的 GatewayConfig，并明确备用 provider=coco2；所有原断言保留。旧探针替换 `_primary` 后同步 `_clients[0]`，避免多 Provider 实现仍调用未包装的客户端。13 项 Mock/MockTransport 测试通过。没有启动真实 smoke，也未新增 Canary 或修改真实请求账本。

## 局限

本轮的主要收益是职责定位和消除可证明的重复，而不是压缩全部生产代码。转发入口与模块边界有行数成本；不以 loop.py 缩短比例宣称整体复杂度等比例下降。安全状态仍跨模块通过同一个 AgentLoop 共享，尚未转成独立的强类型 TurnState；为兼容子类与历史测试，本轮没有同时改变状态模型。

没有执行付费 UAT、真实浏览器 UAT、Canary 或 DeepSeek/GLM 请求；离线结果不证明模型质量或线上延迟。共享 ExFAT Git 元数据仍有 AppleDouble pack index 警告，本轮未修改其共享元数据；实际开发和计量在 APFS。历史资料与原目录未提交修改保留。
