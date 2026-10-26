# Source-Aware Projection 真实语义验收：离线预注册专题

本专题未编号，不创建/修改Phase Tag或ZIP。最初仅获离线准备授权；后续GRANTED_10_REQUESTS的真实结果见下文与独立Live报告。

学习目标是区分“实际SDK保留原user事实”“模型正确使用事实”“助手历史建议与当前用户决定”。来源视图变化不能再用整轮相等比较；新evidence.py用Session外部元数据+SQLite Source ID+Unicode跨度和实际SDK user消息逐项核对。助手/摘要复述不计用户来源保留。未知语义影响保持UNKNOWN。

结构：source_aware_uat.plan固定新照片/音乐/阅读笔记三Case与4/4/2预算；budget复用已有SQLite schema、HTTP gate及SDK adapter，独立plan hash和新路径；prepare只读配置指纹、创建一次空批次、干净提交freeze并只读verify；server显式GRANTED_10_REQUESTS先于凭证/SDK构造，套正式Web/ChatRuntime/AgentLoop；browser_probe只用非生产Origin测试两套新Chrome profile。生产代码和旧Harness不变。

macOS运行：uv sync --frozen；uv run python -m scripts.check_source_aware_uat；uv run python -m compileall -q scripts/source_aware_uat。Playwright在外部临时uv环境运行browser_probe.py，不加入生产依赖。真实SDK在离线专项中仅使用MockTransport，网页请求使用ASGITransport，这不冒充真实浏览器语义验收。

下一步仅查看docs/reports/source-aware-live-uat/acceptance-report.md与冻结证据；未获新的GRANTED_10_REQUESTS不得发送真实模型请求。原L01/L02/L03与原余额不使用。源码/配置/工作区/DB身份冻结后不得修补以继续Live。

## 冻结Live补充

一次执行S01→S02→S03，9/10请求（DeepSeek9，GLM/摘要/Judge0），供应商输入13797、输出1774、总15571，cost=null。真实页面完成消息/Pin确认，原user来源5/5、3/3、4/4保留，冻结最终Task3/3通过。S03首轮却把未确认的“永久保留”列为已确定，全程Decision Classification FAIL；请求保留、最终答对与全程来源分类正确必须分开。

S02旧名只经低信任助手历史进入末请求，最终分为历史而非active；语义影响与因果保持UNKNOWN。局部遮蔽在历史轮数不减时仍正确显示不完整。本批无预算历史省略/协议回退/输出截断，未补跑或使用余下1次。源码与冻结资产未改，自己的服务/profile清理，无执行不确定。

[真实结果与证据](../reports/source-aware-live-uat/live-results/execution-01/acceptance-report.md)独立保存；原预注册及旧Live不改判。不编号、不创建Tag/ZIP，后续另行授权。
