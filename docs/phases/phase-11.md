# Phase 11：MCP 工具权限与 Human-in-the-Loop

## 1. 学习目标与边界

Phase 10 已能发现并执行可信本地 stdio Server 的工具，本阶段学习怎样在实际执行前取得授权。理解 Human-in-the-Loop（人在执行链路中做决策）、Permission Gate（权限关口）、Fail-Closed（条件不明确时拒绝），以及授权与执行成功是两个独立问题。

不新增 Agent 循环、框架或依赖；仍使用锁定的官方 MCP SDK 2.3.0。只管理 MCP 工具调用，不修改内置 read_file/write_file/list_files 的工作区权限。不实现远程 MCP、OAuth、操作系统沙箱或跨进程权限服务。

## 2. 三种权限与 allowlist

| 本地策略 | 行为 |
| --- | --- |
| allow | 通过参数校验后直接调用，不询问审批提供者 |
| confirm | 每一次调用都需要当前参数对应的明确批准 |
| deny | 不注册进模型可见的 ToolRegistry，Manager/Adapter 直接调用也拒绝 |

allowed_tools 决定哪些远端工具可以接入；tool_policies 决定接入后的每次调用如何授权。工具没有进入 allowlist，就算服务器描述说“允许执行”也无效。缺少策略默认 confirm；旧 Phase 10 配置仍可解析，但不再隐含自动授权。MCP 默认关闭。

ToolAnnotations 中的 readOnlyHint、destructiveHint、idempotentHint 是 Server 自述，不能证明工具真实行为，也不覆盖本地配置。模型说“用户已经批准”同样不构成批准。授权检查在 Python 执行边界中执行，不依靠 Prompt 自我约束。

## 3. 配置与运行

在真实 config/config.json 的现有 mcp 段中设置，例如：

```json
{
  "mcp": {
    "enabled": false,
    "servers": {
      "demo": {
        "command": "uv",
        "args": ["run", "python", "-m", "scripts.mcp_demo_server"],
        "allowed_tools": ["add", "echo", "save_note", "read_note", "delete_note"],
        "tool_policies": {
          "add": "allow",
          "echo": "allow",
          "read_note": "allow",
          "save_note": "confirm",
          "delete_note": "confirm"
        },
        "timeout_seconds": 10
      }
    }
  }
}
```

这是配置片段；保留原来的 llm、workspace、session 等字段。模板保持 disabled；用户检查可信程序后显式启用。tool_policies 必须是对象，键必须在 allowed_tools 中，值只能是上述三个字符串；拒绝未知 mcp / Server 字段、非法策略及类型。GatewayConfig 和 Manager 各自校验并深复制，Manager 固定本次进程的策略快照，不向模型开放修改权限的工具。

```bash
uv sync --frozen
# 首次使用才复制模板；已有真实配置不要覆盖：
# cp -X config/config.example.json config/config.json
# 编辑本地凭证、mcp.enabled 和工具策略后：
uv run python mybot/main.py
```

在同一个 CLI 进程内，提出保存、读取、删除笔记的任务。对于 confirm 工具，CLI 展示 Server、工具、策略和转义后的实际参数，只输入小写 yes 才批准本次调用；其他输入拒绝。不要直接单独启动 Demo Server 再输入普通文本：其 stdout 是 MCP 协议通道，由 Manager 启动、持有连接并清理进程。

## 4. 完整架构与调用链

```text
run_gateway（持有 MCP SDK 连接的同一个 asyncio Task）
  → MCPClientManager.__aenter__：initialize、tools/list、校验、按策略注册
  → AgentLoop → ToolRegistry → MCPToolAdapter.execute（Schema 校验）
  → MCPClientManager.call（owner、allowlist/策略、可用性、再次 Schema 校验）
  → 冻结 JSON 参数 → authorize / CLI 或注入审批提供者
  → 从冻结 JSON 重建参数 → SDK Client.call_tool → Demo Server
  → ToolResult → Planning.observe → 配对 Tool 消息 → Session / SessionStore
```

进入 SDK Client、发起 tools/call、退出 SDK Client 始终在同一个 Gateway Task。不能为了等待审批用 wait_for 包住整个 MCP 生命周期，或在子 Task 中进入 SDK cancel scope。CLI 仅把阻塞的 input 放到线程，返回后依然由 owner Task 发起 MCP 调用。

普通无关任务仍走原来的 DIRECT；复杂任务继续使用 create_plan/update_plan 与原有 ReAct。审批没有增加模型分类请求，也不调用真实模型以外的授权服务。

## 5. 核心代码与关键函数

| 文件 | 职责 |
| --- | --- |
| mybot/mcp_client/config.py | 校验 allowlist、tool_policies 与原有 Server 配置 |
| mybot/config.py | 拒绝未知 mcp 顶层字段，构造 GatewayConfig |
| mybot/mcp_client/approval.py | 不可变 ApprovalRequest、安全枚举 ApprovalDecision、参数展示检查、authorize、cli_approval |
| mybot/mcp_client/manager.py | 策略快照、隐藏 deny、真实 SDK 调用前授权、限量内存审计及原有连接生命周期 |
| mybot/mcp_client/adapter.py | 复用 Phase 10 的 JSON Schema 校验和 ToolResult 转换，未修改协议 |
| mybot/app.py | 为网关注入 cli_approval，默认无提供者的其他使用方式不自动授权 |
| mybot/agent/loop.py | 拒绝后停止任务，给本批剩余调用补失败结果，正确结束 Plan/Session |
| scripts/mcp_demo_server.py | add/echo 与有状态的内存笔记工具 |
| scripts/check_approval.py | 真实 stdio 子进程、固定模拟模型与可注入审批测试 |

Manager.call 不信任 Adapter 已经验证这一事实：直接调用 Manager 同样必须匹配保存的 Schema。调用前将参数编码为严格 JSON（拒绝 NaN 等），再解析、校验。审批对象只含不可变的 server、tool、arguments_json 字符串；执行时从先前冻结的 JSON 重新构造字典。即便测试提供者修改调用者的原字典，也只能执行用户检查过的参数。

authorize 只接受 ApprovalDecision.APPROVE 身份，布尔 True、字符串或模型回复都不是授权。每次调用都重新询问，无授权缓存、无“全部允许”、无跨重启令牌。没有提供者、提供者异常、EOF、无交互 stdin/stdout 都拒绝。取消会继续抛出 CancelledError，由原有 owner Task 的上下文退出清理连接，不发送待批工具。

## 6. 参数展示与隐私

审批参数使用 ensure_ascii=True 的 JSON 展示，换行、ANSI 控制字符和 Unicode 双向控制字符显示为转义文本，不能通过参数伪造新的终端行。完整展示最多 4000 字符。明显敏感键（password、token、api_key、secret、authorization 等，包括嵌套对象）及常见凭证外形会遮蔽。

一旦必须遮蔽内容，或完整参数超过展示上限，就不发起人工批准，而是返回 approval_uninspectable。用户不能在关键参数不可见时批准。允许的显式 allow 不要求展示，因此这不是通用的数据脱敏器，也不是防泄漏系统。

manager.audit 返回最近最多 256 条事件的独立副本：server、tool、policy、decision、executed、success、duration_seconds、error。executed 表示进入 SDK 调用，不能证明超时前远端未执行；success 表示返回结果经适配器确认成功。错误只保留安全类别，如 approval_denied、approval_unavailable、approval_error、policy_denied、invalid_arguments、timeout。耗时包括等待审批。默认只在内存保存，不写磁盘、不打印正文和原始异常。

**Session 不是脱敏审计。** 原有 Session/SessionStore 仍保存 Function Calling 原始参数及实际 Tool Result；被拒绝的调用参数也在完整轮次中。启用持久化可能留下明文私人内容。本阶段没有扩大其范围，也没有承诺所有存储已经脱敏；测试全部使用合成数据、临时目录，不读取真实聊天历史。

## 7. 拒绝如何维护消息与 Planning

获得权限只允许执行一次调用，不等于操作成功。SDK isError、参数错误、超时仍是失败 ToolResult；批准不能成为 Plan 的成功证据。

收到 permission_denied 后，AgentLoop 不再请求模型重试本轮：拒绝调用保留自己的 Tool Result，本批后续每个调用都补上 approval_cancelled 失败结果，不再实际执行（包括原生文件工具和 update_plan）。因此 assistant.tool_calls 和 tool.tool_call_id 一一配对，不留下孤立调用。随后用明确“未获批准、任务已停止”的回复收尾，Plan 未完成不能宣称成功，完整轮次按原有机制进入 Session/SessionStore。

本批先前已成功执行的只读操作不回滚；对于之前已批准的修改，同样没有事务回滚。下一条用户输入重置 Plan，但不重用批准。/clear 清除会话和 Plan，不改变策略、不清除远端内存笔记、不重放工具。恢复 Session 只恢复历史文本；不恢复授权和 Server 内存。

## 8. Demo 的真实状态验证

save_note(key, content) 将笔记写入当前 Server 的字典；read_note(key) 返回内容，缺失时失败；delete_note(key) 删除已有条目。key 限制 1–100 字符，content 最多 2000 字符，最多 100 条笔记。没有文件、网络或 shell 操作；进程重启字典为空。

自动化测试真实启动 Demo Server，并在操作后通过 MCP 读回状态：

| 修改操作及审批 | 随后的真实 read_note 结果 |
| --- | --- |
| 拒绝 save_note | 查不到条目，未发送修改的 SDK 调用 |
| 批准 save_note | 返回 approved-content |
| 拒绝 delete_note | 原有 keep 内容仍存在 |
| 批准 delete_note | 查不到条目 |

测试还检查：用户检查 original/approved-value 后，提供者把调用者字典改为 swapped/UNAPPROVED，实际仍写入 original，swapped 不存在；第二个用户任务不能沿用第一个任务的批准。批量调用中已成功的 add 保留，拒绝 save 后原生 write_file 也不执行，所有六个 Tool Result 与 ID 配对，磁盘历史可通过原验证器重新加载。

## 9. macOS + uv 测试与实际结果

```bash
uv run python -m scripts.check_approval
uv run python -m scripts.check_phase
uv run python -m scripts.test_phase_archives
uv run python -m compileall -q mybot
```

Phase 11 新增 25 项 unittest，覆盖配置、默认 confirm、显式 allow、单次批准/拒绝、deny 隐藏及直接调用、非终端、非法输入/EOF/异常、参数冻结、跨任务授权、实际笔记状态、Plan、批量配对及持久化、clear、重启、审计、取消与进程 PID 清理、Demo 长度限制。Phase 10 的 17 项真实 MCP 测试继续通过，测试夹具显式声明 allow，保留原有机制测试的目的。

全量 Phase 1–11 共 156 项 unittest 及 Phase 1/2 的断言检查；全部离线运行。归档设施另验证工作区不干净/重复 Tag/重复 ZIP/恶意 ZIP/敏感历史等拒绝路径。未使用真实 LLM API，也未将固定模拟回复当作真实模型能力成绩。归档前运行结果、独立还原结果记录在 AI_HANDOFF.md；归档脚本会对提交源码再执行冻结安装、编译及全部离线回归。

## 10. 常见问题与限制

- 旧配置突然要求确认：缺少 tool_policies 默认 confirm；需要明确设置某工具 allow 才跳过。模板仅 add/echo/read_note 为 allow，写/删为 confirm。
- 重定向输入时无法批准：stdin/stdout 任一不是 TTY，CLI 默认拒绝。自动化用受信任的可注入提供者，不用管道 yes 绕过检查。
- 没看到审批提示就拒绝：可能无 TTY、没有提供者、内容过大或敏感，检查安全错误类别；不要把无法检查的参数盲目设为 allow。
- 审批没有等待时限：可以拒绝或 Ctrl-C；终端 input 线程在取消后可能仍需终端输入/EOF 才能退出，SDK 连接由 owner Task 清理。本阶段不实现终端编辑器或非阻塞 stdin 协议。
- 客户端拒绝表示没有发送该工具调用；已发送调用遇到断连/超时不能证明服务端没有产生效果。不要自动重试有副作用操作。
- 客户端审批不是操作系统沙箱。可信 Server 启动与初始化阶段就具有本地用户权限；即使所有工具 deny，启动恶意程序依然危险。
- 敏感键检测是保守启发式，不保证识别任意私人内容；审批展示、Session 明文、外部 Server 自己的行为是不同边界。
- ExFAT 不能保证 POSIX 私有权限，macOS 也可能生成 ._*；归档排除这些文件，复制设置 COPYFILE_DISABLE=1，独立验证优先使用 APFS 临时目录。

## 11. Phase 10 → Phase 11 与独立复习

保留原先的 stdio/Tools/Schema、命名空间、串行执行、owner Task、错误处理及 12000 字符结果上限。新增本地调用策略、一次性审批、安全展示、内存审计、真实有状态演示及拒绝收尾；不引入第二套工具框架，不改变模型工具协议。不进入 Phase 12。

```bash
# 由阶段提交的干净工作树执行，拒绝覆盖已有归档：
bash scripts/save_phase.sh 11 "MCP Tool Permissions and Human-in-the-Loop"
bash scripts/restore_phase.sh 11
cd ../mybot-mini-learning/phase-11
uv sync --frozen
uv run python -m scripts.check_phase
```

Tag 为 phase-11，完整源码 ZIP 为 ../mybot-mini-snapshots/phase-11.zip。快照包含代码、示例配置、锁文件、技能、教程和离线测试，不包含真实配置、笔记状态、Session、审计或用户未提交修改。

archive-ready: true
