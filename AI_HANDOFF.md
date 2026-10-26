# AI_HANDOFF

## 当前状态

独立分支codex/streaming-protocol-shutdown-fix，基线2b08360ee87aba28a9935f8a2b06fae2467883b4。实现协议脱敏诊断、有界SSE与操作员TTY关闭修复。真实授权0，未连接Provider。原R01 FAIL/HALT、1/8及Case running保留，剩余7次不使用。

## 实现与验证

streaming.py固定错误枚举、8块结构ring，合法终态+自然EOF+close才可信；预算/存储/未知宿主异常不吞为Provider错误。无通用语义或真实DeepSeek兼容修复声明，ORIGINAL_R01_ROOT_CAUSE UNKNOWN。

Web有限2秒SSE+250ms原生重连、Last-Event-ID/reset，错误面板仅传安全代码；Runtime同Task MCP/SDK清理deadline，HALT不阻止清理自身任务。scripts/local_web_process处理继承TTY时uv不转发SIGINT，只对身份/出生时间/端口复核成功的自己子服务发SIGINT。

新协议39、关闭11、SSE8专项；原Streaming33与Web/Steer30最小回归通过。真实headed独立Chrome A–G合成通过，9次Mock HTTP、真实0。SSE旧机制与TTY转发问题分别复现。全量check_phase与独立补充最终稳定版本验收待Acceptance完成；中途修改源码引发冻结测试拒绝，不作最终PASS计数。旧断言保留，生产依赖/旧UAT脚本/旧报告不改。

## 下一步

完成稳定源码全量回归、脱敏报告/审计与Acceptance提交，Push核对远程。专题docs/phases/streaming-protocol-shutdown-fix.md；报告docs/reports/streaming-protocol-shutdown-fix/。本轮不运行任何旧Live、prepare/freeze或修复旧账本；未来真实验证必须另立新批次与新授权。不合main、不改历史Tag/ZIP。
