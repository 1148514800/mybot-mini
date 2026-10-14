# AI Handoff

## 当前状态

Phase 06 Context Management 已完成：phase-06 Tag 指向 ccd6872，同级 mybot-mini-snapshots/phase-06.zip 已保存并独立还原验证。Phase 01–05 保持不变，不进入 Phase 07。context.enabled 默认 false，本地配置及模板已补齐。

## 实现与修改

- agent/context_manager.py：JSON 字符计量含消息结构/参数/Schema；完整当前任务保护、工具正文请求副本裁剪、旧整轮摘录、近期优先、总预算二次校验。
- agent/loop.py：每次 create 前生成 llm_messages，与 canonical 分开；数字统计，节选/省略展示提示不改原回复；预算失败关闭 Plan，不提交半轮。
- config.py、模板：context 字段严格类型/范围检查。
- scripts/check_context.py、check_phase.py：18 项实际模拟请求检查；旧回归明确 context=false。
- docs/phases/phase-06.md、索引、README：完整教程与局限。
- Session/SessionStore JSON v1、Planning/真实工具和权限不改，无新依赖。

## 测试

Context 18 项通过；合成请求计量 13431→6428，预算8000，保留近期2轮。覆盖消息配对、原文/JSON/重启、System/User/Plan 保护、Schema、每次 ReAct、超预算不发送、工具节选和实际证据、clear、配置/异常。Phase 01/02 回归、Session 12 项、Planning 12 项、Persistence 16 项通过；开发源码编译通过（排除 AppleDouble）。归档安全测试通过，实际 ZIP 独立还原后 uv sync --frozen、完整源码编译和 Phase 01–06 统一回归均通过，不含真实 Session/配置或用户未提交文件。真实 API 手工测试未执行。

## 决策与局限

只深拷贝请求，不改 Session/Plan；旧完整轮次临时替换为普通 assistant 来源摘录，不升级系统指令或假冒工具结果。近期保留是优先而非硬保证；没有空间时展示省略提示。工具正文最低可缩到128字符，ID/arguments/System/User 不剪；仍超预算明确失败。字符不是 Token，输出 tokens 配置不变，需预留供应商窗口；摘录可能丢事实，不能保证全文分析或语义质量。已执行工具副作用不回滚。

## 环境与用户改动

macOS/zsh、Python3.12+、uv，运行 uv run python mybot/main.py。context 开关修改重启生效；原 session.persist/path/max_turns 配置保留。app.py、USER.md 等用户修改不提交；真实 Session/配置不输出、不归档。ExFAT ._* 尽量 COPYFILE_DISABLE=1 减少，归档排除元数据，独立验证用 APFS 临时目录。

## 下一步

Phase 06 已完成，后续由用户指定任务。不覆盖旧 Tag/ZIP、不重复实现 ContextManager、不进入 Phase 07；历史原理见 docs/phases。
