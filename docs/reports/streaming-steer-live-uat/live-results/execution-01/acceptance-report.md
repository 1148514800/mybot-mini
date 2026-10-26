# Streaming & Steer Live UAT — FAIL / subsequent cases BLOCKED

收到本轮明确GRANTED_8_REQUESTS后，复用唯一原冻结批次执行R01一次。真实连接coco / deepseek-v4.1-flash，1次逻辑、1次物理、1次HTTP。R01收到328个真实SDK Chunk并显示浏览器预览，但运行终态provider_error，未取得可信完整回复；原账本halt=protocol_or_runtime_failure。按冻结停止条件，R02–R04未启动，无补跑或新增提示。剩余7次不使用。

输入HEAD `5a58801420f2ea1047f8c9f5e3c8ed2fd6fb0095`，Preregistration `75e79d2ed7fd6c14beef326f025667c3f61085ba`，分支 `codex/streaming-steer-live-uat`。原消息、配置、源码、时序、评分、Fixture、数据库inode完整，核验见integrity-evidence.json。prepare/freeze均未重做；原OFFLINE报告、历史Live结果保持。

R01协议终到端FAIL：可观测stream=True及include_usage=True发送、SDK异步流与预览成立；终态完整性FAIL。SDK observer见finish_reason=stop，但消费提前退出且eof=false，不能只凭finish字段判成功。Usage全部null，实际费用null。未发生备用、隐藏重试、工具或模型摘要。

UI局部PASS：同一浏览器performance时钟提交到首次DOM预览约3.461秒，首SDK Chunk约2.344秒且无文本；首内容约2.356秒，首SSE预览约3.257秒/65块。SDK首Chunk→DOM差值UNKNOWN，不能跨时钟相减；R01无屏障。看到实时文字不代表最终回答完整。

清理维度FAIL/部分已核验：SDK close=true且reservation已结算（failed），但正常SIGINT关闭本轮uv launcher等待25秒未退出，未取得exit0。后续只读核实自身服务进程均不存在、8899释放、Lease可重新获取、临时Chrome及profile已清理；退出方式/退出码UNKNOWN，Case账本仍running，不手工修复。没有execution_uncertain记录或残留reservation；不宣称全流程正常关闭成功。

最优先问题是查明真实流末尾为何被consumer拒绝并保留脱敏协议错误类别，再修复可审计的服务关闭。当前observer只记录GeneratorExit，不能确定具体拒绝分支或归责Provider。R02工具组装/Steer语义、R03不应用、R04真实取消仍未验证。本轮不修源码、不再连接真实Provider。

完整维度见case-results.md；预算、时钟、浏览器和安全证据分别独立记录。提交及远程HEAD在最终交付核对（本报告不自写其自身Commit）。
