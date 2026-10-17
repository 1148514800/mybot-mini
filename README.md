# MyBot

MyBot 是一个简洁的本地命令行 AI 助手，通过 OpenAI 兼容接口调用模型，并可在指定工作区中读取和写入文件。

## 需要的软件

- Python 3.12 或更高版本
- OpenAI 或兼容服务的 API Key

## 安装与配置

```bash
uv sync
cp config/config.example.json config/config.json
```

编辑 `config/config.json`，填写提供商的 `api_key`、`base_url` 和 `model`。真实配置文件不会提交到 Git。

Windows PowerShell 可使用：

```powershell
uv sync
Copy-Item config\config.example.json config\config.json
```

## 启动

```bash
uv run python -m mybot.main
```

输入问题并按 Enter 开始对话，输入 `exit` 或 `quit` 退出，输入 `/clear` 清空当前会话。进程内默认保留最近 6 个完整用户轮次（含工具请求和结果），默认退出后不保存历史；开启 session.persist 后可跨重启恢复。Agent 可以调用 `read_file` 和 `write_file`，文件操作限制在配置的 `workspace.path` 目录内。

## 配置

```json
{
  "debug": false,
  "session": {"max_turns": 6, "persist": false, "path": "./.mybot_state/session.json"},
  "llm": {
    "provider": "siliconflow",
    "max_completion_tokens": 2000,
    "request_timeout_seconds": 60,
    "max_react_steps": 10,
    "providers": {
      "siliconflow": {
        "api_key": "YOUR_API_KEY",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen3-235B-A22B-Instruct-2507"
      }
    }
  },
  "workspace": {"path": "./workspace"}
}
```

将 `config/config.json` 顶层的 `debug` 设置为 `true` 开启调试日志，设置为 `false` 关闭，默认关闭。修改后重启程序生效。日志包含模型耗时、token 数、工具参数及执行结果摘要；写入参数 `content` 仅显示字符数。调试开关统一由配置文件控制，不再读取 `MYBOT_DEBUG` 环境变量。


## Phase 学习归档

学习索引与独立运行方法见 [docs/phases/README.md](docs/phases/README.md)。完成阶段、验证并提交相关文件后，在干净工作区执行：

```bash
bash scripts/save_phase.sh 2 "自定义 Agent 工具 list_files"
bash scripts/restore_phase.sh 1
```

保存会创建唯一 Tag 并将完整源码 ZIP 写到 `../mybot-mini-snapshots/`；还原到 `../mybot-mini-learning/phase-01`，不修改开发分支，拒绝覆盖已有版本。Phase 01–17 已分别归档；已存在的 Tag 和 ZIP 不可重复保存。

归档设施验证命令：`uv run python -m scripts.test_phase_archives`。

对话历史轮数通过 `config/config.json` 的 `session.max_turns` 调整，默认 `6`，必须是正整数。修改后重启生效；这是保留历史的轮数，不是单次任务工具循环的 `llm.max_react_steps`。

复杂多步任务可由模型调用 `create_plan` 建立 2–6 步计划，并通过 `update_plan` 显示执行进度；简单任务直接执行，不增加独立分类请求。步骤完成需要实际工具成功结果；失败或未验证会明确报告。每条用户任务重新开始计划，`/clear` 同时清空历史和计划。详见 [Phase 04](docs/phases/phase-04.md)。

Session 持久化默认关闭。配置 `session.persist=true` 并重启后，完整历史轮次保存到 `session.path`（默认项目根 `.mybot_state/session.json`，必须在 workspace 外）。`/clear` 同时清空磁盘历史；JSON 损坏会报错并保留原文件。恢复不会重放旧工具或恢复 Plan 状态。详见 [Phase 05](docs/phases/phase-05.md)。自定义状态目录也应加入 `.gitignore`；ExFAT 无法保证 POSIX 私有权限，聊天历史以明文保存。

Context Management 默认关闭。配置 `context.enabled=true` 并重启后，每次请求检查消息及工具 Schema 的字符预算。默认 max_chars=40000、recent_turns=2、summary_max_chars=1500、tool_result_max_chars=4000。只压缩请求副本，Session/磁盘仍保存原文；无法满足预算时停止并报错。字符数不是精确 Token 数，需为 max_completion_tokens 预留模型窗口。详见 [Phase 06](docs/phases/phase-06.md)。

Skills 默认关闭。设置 `skills.enabled=true`（path 默认 ./skills）并重启后，模型获得 name/description 索引，可通过 load_skill/read_skill_reference 按需读取说明和参考资料，再使用原有文件工具。示例为 file-summary 与 code-review。没有脚本执行或额外模型分类调用；Context 开启时技能正文不裁剪、超预算明确失败。详见 [Phase 07](docs/phases/phase-07.md)。

## Agent Evaluation

```bash
uv run python -m scripts.eval_agent
uv run python -m scripts.check_evaluation
```

默认 Offline 使用固定模拟响应与隔离合成文件，仅验证评测机制，不能当作模型能力成绩。A/B 对比 Skills 关闭/开启，报告保存到忽略的 runs/evals/。显式 --live 才调用当前配置的真实模型，可能收费；使用 --max-cases、--max-requests、--timeout、--repeats 控制运行。详情见 [Phase 08 学习文档](docs/phases/phase-08.md)。

Evaluation 2.0 使用 JSON v2，分别报告 task_success、process_clean、instruction_followed 和 strict_pass；Auto 不加载 Skill 也可通过。使用 --case-ids 选择任务、--groups off,auto,guided 选择实验组。Guided 追加显式技能要求，不能直接当作纯技能收益。--analyze-report 可只读重算旧报告，缺失原因保留 unknown。详见 [Phase 09](docs/phases/phase-09.md)。

评测诊断会区分 JSON/字段格式失败、证据未匹配与产物差异。可用 --retain-artifacts runs/evals-artifacts 显式保留内置合成任务输出（默认不保存正文）。格式不合法的审查不计作真实漏报，任务评分仍严格。见 [诊断说明](docs/evaluation-diagnostics.md)。

## 本地 MCP Tools

mcp.enabled 默认 false。显式开启后，通过配置的可信stdio Server发现allowed_tools，并注册为mcp__demo__add等命名空间工具。command/args分别配置，cwd固定项目根，使用官方mcp2.3.0 SDK。启动程序具有用户权限，不继承内置文件工具的workspace隔离；Demo提供add/echo及仅进程内保存的save_note/read_note/delete_note。配置错误或调用异常会清理连接，断连后需重启，/clear只清会话。运行测试：uv run python -m scripts.check_mcp。详见 [Phase 10](docs/phases/phase-10.md)。


Phase 11 增加本地 `tool_policies`：`allow` 直接执行、`confirm` 每次确认、`deny` 隐藏并拒绝执行。缺少策略默认 confirm；旧配置仍有效，但自动执行需显式 allow。模板中 add/echo/read_note 为 allow，save_note/delete_note 为 confirm。CLI 只接受本次小写 yes，非交互/缺少提供者/无法安全完整展示参数均拒绝；拒绝后停止本轮后续调用并维护 Session 配对。审计只保留限量内存元数据，Session 仍可能持久化原始参数。测试：`uv run python -m scripts.check_approval`。详见 [Phase 11](docs/phases/phase-11.md)。


Phase 12 增加 `transport="streamable_http"` 与本地配置的 `url`；未写 transport 仍为 stdio。两种连接共用工具发现、Schema、Phase 11 审批、审计和原执行循环。HTTP 仅允许字面量回环 HTTP 或用户显式配置的可信 HTTPS，禁用环境代理/隐式认证，拒绝全部重定向，不自动重连或重试工具。先在另一终端运行 `uv run python -m scripts.mcp_http_demo_server --port 8765`；退出 mybot 不会终止该 Server。模板保留 MCP 关闭，同时示例两种 Server；启用后所有配置的 Server 都须可达，不用的条目应移除。测试：`uv run python -m scripts.check_mcp_http`。详见 [Phase 12](docs/phases/phase-12.md)。


Phase 13 增加可选 `auth={"type":"bearer_env","token_env":"MYBOT_MCP_TOKEN"}`（仅HTTP；省略或none仍匿名）。只从显式环境变量读取连接快照，Token不写配置/工具参数；认证不会绕过Phase 11审批。HTTP非SSE响应在解码前限制为2MiB实际字节，不依赖Content-Length；拒绝压缩响应，SSE保留SDK单事件限制。教学认证Server：`MYBOT_MCP_DEMO_TOKEN=test-local-token uv run python -m scripts.mcp_http_demo_server --port 8765 --require-token-env MYBOT_MCP_DEMO_TOKEN`，仅用合成Token进行本地明文测试。专项：`uv run python -m scripts.check_mcp_auth`；完整说明、配置与限制见 [Phase 13](docs/phases/phase-13.md)。


Phase 14 增加预注册公共Client的 `oauth_pkce`：复用MCP SDK的发现、PKCE S256、state/iss验证、授权码交换及内存Token刷新/轮换。浏览器打开前先绑定固定回环Callback并要求CLI确认；工具401/403不重新授权或重放，Phase 11审批仍有效。MCP与OAuth端点分别白名单校验，保留Phase 13响应限制。教学环境：`uv run python -m scripts.mcp_oauth_demo_server`；本地配置片段为 `config/mcp.oauth.example.json`（仅mcp块，需合入真实配置）。专项：`uv run python -m scripts.check_mcp_oauth`。没有动态注册、CIMD或跨重启Token存储，重启需要重新授权。见 [Phase 14](docs/phases/phase-14.md)。


Phase 15 增加可选 `mcp.discovery`（默认关闭）：本地Catalog复用已验证MCP定义，通过 `search_mcp_tools` 搜索、`activate_mcp_tools` 原子替换当前任务可见工具；完整Schema从下一次模型请求起暴露。同批激活不能立即调用新工具，审批权限不变；任务结束和/clear清空激活。35工具示例片段见 `config/mcp.discovery.example.json`，需自行合入本地配置。测试：`uv run python -m scripts.check_tool_discovery`；离线对比：`uv run python -m scripts.compare_tool_discovery`。Schema字符减少伴随额外模型轮次，未测真实Token/费用或模型能力，见 [Phase 15](docs/phases/phase-15.md)。

## 工具检索与合成 Agent 评测（Phase 16）

`mcp.discovery.retrieval_mode` 可选 `literal`（默认，兼容 Phase 15）、`bm25`、`hybrid`。Hybrid 是固定双语词典加 BM25，不使用 Embedding、模型翻译或额外网络请求；不会改变工具权限和审批。

```bash
uv run python -m scripts.compare_tool_retrieval
uv run python -m scripts.evaluate_tool_agent
uv run python -m scripts.check_tool_retrieval
uv run python -m scripts.check_tool_agent_eval
```

以上默认离线，排名指标与 Agent 任务成功率独立报告。新 Harness 的 Live 必须同时显式指定 `--live --confirm-api-cost`，只连接内置合成 stdio Demo，关闭 Session 持久化、Skills、DEBUG和SDK重试；受请求数、案例数、重复次数、输出Token及总时长限制。开发验证未运行真实 LLM API。完整算法、实测结果、预算参数、Usage/缓存/估价限制见 [Phase 16](docs/phases/phase-16.md)。

## Adaptive Tool Routing（Phase 17）

显式配置 `mcp.discovery.enabled=true`、`routing_mode="adaptive"` 后，Agent 在每个新任务首轮模型请求前，使用同一个 Catalog/检索索引预选预算内的完整 MCP Schema。建议显式选择 `retrieval_mode="hybrid"`。缺省仍是 manual，旧 Eager/Progressive 行为与评测入口保持兼容。

Router 根据目录数量、完整 MCP Schema 上限与原 ContextManager 总预算选择 small_eager、ranked_preselect 或 manual_fallback。没有额外模型请求或自动业务执行，不改变审批；模型仍能搜索并完整替换激活集合，请求级快照约束保留。

```bash
uv run python -m scripts.compare_adaptive_routing
uv run python -m scripts.check_adaptive_routing
```

新对比入口默认 Eager / Progressive Hybrid / Adaptive Hybrid，使用相同12条合成任务、固定模型和真实本地 stdio；自动预选指标与显式搜索/激活分开，未知 Token/费用保留 null。算法、两层预算、Gold 隔离、实际对比与限制见 [Phase 17](docs/phases/phase-17.md)。开发验证不运行 Live。


## Tool Routing Confidence（Phase 18）

显式 `selection_policy="selective"`（同时启用 discovery 与 adaptive）才使用证据门控、安全弃选及覆盖感知预选；缺省 `legacy` 保留 Phase 17。只有 Strong 证据允许自动暴露完整 MCP Schema；弃选后原 search/activate 继续可用，权限与审批不变。

```bash
uv run python -m scripts.compare_selective_routing
uv run python -m scripts.evaluate_tool_routing
uv run python -m scripts.evaluate_tool_agent --case-set routing --modes adaptive_hybrid,adaptive_selective_hybrid
uv run python -m scripts.check_routing_confidence
```

独立60例路由集与10例Agent挑战集分别报告；保留原12例核心基准。Selective减少无关预选，但会漏掉有用工具并增加手动探索请求，不宣称全面优于Legacy。规则、分母、完整实测及限制见 [Phase 18](docs/phases/phase-18.md)。本阶段完全离线。
