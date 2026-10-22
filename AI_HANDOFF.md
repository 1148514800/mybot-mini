# AI_HANDOFF

## 当前目标与状态

Web Chat 已完成实现及离线/真实浏览器验收，分支 `codex/web-chat-ui`，基线 `d4726669464bb83fd86d94e9ef31090dc4e7c782`。正式入口 `uv run python -m mybot.web --port 8765`，访问 http://127.0.0.1:8765。本任务按 Implementation、Acceptance 两个提交交付并推送独立分支，不合并 main，不属于新 Phase，不修改历史 Tag/ZIP。

Implementation `027889b6831754f53647de32a82b1e00e9af78f7`；Acceptance 为本快照所属报告提交。

## 实现与架构决策

新增 `mybot/web/`：Starlette HTTP/SSE、中文三栏响应式界面、深浅主题、安全 Markdown/代码复制、真实工具卡片/Plan/Diff/测试状态、受控单次浏览器审批、独立 Session 与停止/刷新恢复。正式 runtime 直接使用原 GatewayConfig、build_gateway_client、AgentLoop.handle_message、Registry、Context/Skills、Planning、MCP、Controller、Receipt 与 Journal。Loop 只新增可选白名单观察回调；CLI 缺省行为保留，不解析 print 或启动 CLI 子进程。

每进程单任务 lease 在 Agent/MCP/client 清理完成后释放，执行或清理不确定则禁止新任务。每轮工具、Controller、Receipt scope、模型客户端独立；同一对话保留真实 Session。fallback sticky 仅该轮。历史仅内存，最多20会话、64条展示消息/会话、128条当前任务事件，不读写 CLI 磁盘历史。浏览器 localStorage 仅主题。

仅127.0.0.1；Host/Origin、HttpOnly SameSite cookie、CSRF、授权 SSE、CSP、固定资源路由、输入/事件大小限制与凭证/能力脱敏。命令及 MCP 审批沿用原策略；nonce 单次有时限，无预批准/缓存/自动 yes。Undo 和旧文本控制命令明确拒绝；CLI Undo 不受影响。Preview 不当成写入，测试成功不当成 Strict Success。

修改：Web 模块、Loop/Plan 观察适配、显式 Starlette 依赖及 lock、`scripts/check_web_ui.py`、全量入口追加、README、`docs/web-ui.md`。原 Controller、Patch 发布器、Journal、命令/MCP 安全策略及 Strict 评分源码未改。

## 验证与保护

专项53/53；全量1293/1293、35套件、零跳过，原1240项全部保留；compileall、diff 检查通过。真实 AgentLoop + 合成模型 + 原生 Receipt/Seatbelt/stdio MCP/本地 HTTP/SSE。浏览器实际检查桌面深浅主题、390px手机、Markdown/XSS、复制、长代码滚动、多行输入、切换/清空、停止/刷新及一次人工点击批准临时测试命令。

真实模型HTTP 0，TTY yes 0，浏览器临时 fixture 交互批准1次；未使用旧 Benchmark 额度。1043保护文件哈希无变化，main、26 Tag、53 ZIP/AppleDouble、原13及最近8 Attempt raw 均保留。原工作区 `mybot/app.py`、`workspace/instructions/USER.md` 用户修改未触碰。不得重跑旧实验或伪称 Live 验证。

## 文档、限制与下一步

使用说明 `docs/web-ui.md`；验收报告及6张实际截图位于 `docs/reports/web-chat-ui/`（Acceptance 提交）。不支持公网、多租户、附件、持久化 Web 历史或 Web Undo；Markdown 为基础子集，回复非 Token 流式。单进程 lease 不协调其他 CLI/服务进程。真实供应商连通性与付费聊天按本轮0请求限制未验证；用户配置原本地模型凭证后自行启动使用。后续扩展需保留审批及清理屏障，勿把当前测试范围称为整体 Strict 成功。
