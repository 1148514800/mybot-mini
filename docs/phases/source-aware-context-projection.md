# Source-Aware Context Projection 学习专题

本专题接续持久会话Live发现的信息来源损失，未编号，不是新的Phase Tag/ZIP归档。当前工程和验收结果以专题acceptance-report.md为准，旧Live结论不变。

## 学习目标与Agent概念

区分持久化事实、模型参考视图、当前授权。SQLite保存聊天不意味着模型看到全部历史；撤销Pin也不是让模型物理遗忘。source_message_id+Unicode跨度用于确定具体来源，不可用文本相同代替身份。历史助手建议不等于用户确认，任何聊天和Pin都不赋予Tool Authority。

## 架构与关键函数

Session.HistoryTurn在消息dict之外携带宿主来源ID。SessionHistory.identify_turn绑定当前接受的user事件；ModelContextProjection.turns重启后取真实ID。SessionHistory.context_turns委托storage.context_projection.project_history，在临时copy中校验来源、遮蔽span、处理助手复述与工具组回退。原始消息/事件没有改写。

AgentLoop先做安全投影，再给ContextManager构造实际请求；ContextCompactor只接收这些安全历史，不能先摘要原始旧规则。TokenCounter仍计入全部参考、schemas和输出保留。resources.context同时供CLI和Web显示局部遮蔽、协议省略和失败原因。同类Pin的multiple_same_category/unassessed是中性状态。

## macOS + uv 安装运行

```bash
uv sync --frozen
uv run python -m scripts.check_source_aware_projection
uv run python -m scripts.check_pin_lifecycle_context
uv run python -m scripts.check_projection_protocol_integrity
uv run python -m scripts.check_phase
uv run python -m compileall -q mybot scripts
node --check mybot/web/static/app.js
```

浏览器合成服务必须使用全新0700私有临时目录：`uv run python -m scripts.source_projection_browser_server --root <private-temp> --port 8897`。它显式注入SyntheticClient、独立SQLite与workspace，不读取Provider凭证。外部Playwright通过全新临时Chrome profile操作真实页面，不使用用户默认配置。Playwright是可选的外部验收环境，不加入生产依赖。

## 实际案例与常见问题

公开产品信息单元构造新Fixture：旧命名+分页/排序/空状态，新命名+中文/相对路径。原基线实际合成请求替换时损失3、撤销后累计5；新请求两阶段均保留5/5，SQLite原消息相同。工具轮可能保守丢失整组而不是5/5，应查omitted_protocol_turns。正文截断、脱敏或没有来源ID时不能猜测跨度；查source_mapping_failure_reasons。预算不足时也可正常丢历史，应区分history_turns_omitted与redacted_source_spans。

## 与上一阶段的变化及边界

以前按文本命中删除整轮；现在精确遮蔽来源片段、明确生命周期和助手信任级别。新增42项专项，合成真实浏览器A–E；完整结果见专题报告。没有重新开发存储、引入LLM分类、改变Tool审批或花费真实模型额度。助手语义改写尚不能可靠清除，离线改善不代表Live语义已验证。
