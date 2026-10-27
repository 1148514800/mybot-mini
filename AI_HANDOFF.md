# AI_HANDOFF

## 当前目标与状态

codex/provider-chain-failover，基线45da46ec4bdae88f0110edd7e34c9c5c95247ad5。通用Provider链开发完成，相关Mock专项243项通过；真实API0，不建立Canary、批次或冻结，不跑完整Benchmark。

## 实现

mybot/provider_failover.py 按默认项和JSON声明顺序循环各Provider一次，各自Key/URL/model、成功后任务内保持、新任务重置。保留旧双Client评测构造接口，生产路径无coco/coco2分支。网络/超时、401/403/404/408/429/5xx及原生确认关闭后的流中断可切换。宿主错误、权限、Schema、Stop、关闭不明均停止。

每Provider完整请求窗口，不再/2；AgentLoop逻辑窗口覆盖整个链但仍受Controller剩余任务时间和Web截止约束。原consume未完成时不交付工具调用；安全关闭后撤销部分预览，重新生成当前响应，不拼接、不重放已完成工具。SDK retries0，每个失败尝试仍原生预算/HTTP/Token计数。RuntimeAccounting、AgentLoop、WebRuntime使用实际活动配置；全链Key参与脱敏。

修改：provider_failover.py/runtime_accounting.py/agent/loop.py/web/runtime.py/static/app.js；新增check_provider_chain.py19项并更新相关新合同断言；README和docs/provider-failover.md。原Patch/权限/审批/工具实现无改动。

## 验证与限制

Failover/Chain/Streaming/Accounting/诊断/Legacy/Web/Token专项243通过，compileall、JS、diff及凭证资产审查通过。覆盖三Provider、整流超时、默认回绕、原生Coding预算、Stop、关闭失败、宿主准入/预览错误不回退、已执行工具不重放与三模型Key脱敏。没有真实部署/API兼容性保证；未知Usage仍null，协议错误不是无限重试。

原C02唯一Live FAIL（4/18、Revision0、第四流取消）及历史报告/账本保持；剩14次不使用、不转移、不补跑。旧冻结需要原历史分支源码，本功能分支不重跑或重冻C02；main/Tag/ZIP/共享AppleDouble不修改。

## 下一步

本轮只交付功能代码和离线验证，Commit/Push新分支，核对远程HEAD。若以后需要真实部署验证，另行明确授权；不得从旧C02余额或授权推导。配置/使用说明见docs/provider-failover.md，不引入第二AgentLoop或自动工具批准。

本机只读配置审计另发现：主仓库真实config/config.json第29行JSON格式错误，未修复或提交凭证文件；实际运行前需修正自己的配置。Mock不依赖真实配置。
