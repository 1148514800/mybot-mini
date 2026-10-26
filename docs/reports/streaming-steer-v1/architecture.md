# Streaming & Steer v1 architecture

新增agent/streaming.py和agent/steer.py，AgentLoop只增加接入点，不另建Agent循环、Memory或授权系统。web.streaming.enabled与web.steer.enabled均默认false；示例配置显式展示关闭状态，GatewayConfig拒绝非布尔及未知子字段。

调用链：Web用户请求→原ChatRuntime/WorkspaceLease→AgentLoop原预算门→RuntimeAccounting.dispatch→SDK create(stream=True)与同作用域consume→完整规范化响应→原工具Registry/审批或可靠最终保存。异步迭代消费不产生第二次物理请求。语义摘要仍走原非流式、显式授权路径。

Steer链：带原Cookie/Origin/CSRF的用户POST→绑定当前Session/Turn的SteerInbox→schema v2审计事件→下一安全边界→丢弃尚未执行的工具批并补齐明确失败结果→下一步构造真实user来源参考→Token与Controller预算→物理请求准入后标applied。无后续步骤则not_applied，无自动新Turn。

参考仅借鉴边界：[Codex App Server](https://learn.chatgpt.com/docs/app-server)使用活动Turn身份约束和独立增量事件；[DeepSeek Harness Agent](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent/README.md)区分下一Turn输入与下一步骤输入，并把预览与持久化分开。本项目未移植其完整框架、重试或持久Inbox。

真实DeepSeek/coco与GLM/coco2部署兼容性UNKNOWN；本轮仅OpenAI Python SDK 2.32.0、httpx 0.28.1及Synthetic/MockTransport。Python3.12.14，生产依赖与uv.lock未改。
