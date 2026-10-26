# Remaining risks

真实Provider流、Usage、Tool Call、Steer遵从及取消计费均未验证。NOT_GRANTED时不能为消除未知而发送试探请求。

SafePreview按行释放，可能直到终态才可见；届时必须分开报告协议PASS与UX FAIL。8秒屏障是受控时序，不是自然网络延迟，每物理流独立记录实际等待。首Chunk若已终态则无屏障，前提不满足须BLOCKED，不能重跑。

当前DOM与SDK测量跨进程，差值无可靠关联时UNKNOWN。服务端预览发出可以同域计时但不能冒充DOM可见。

R02依赖真实模型生成工具与后续步骤，4次额度内可能未完成；queued、applied、语义遵从不能互相替代。Registry收紧是UAT环境适配差异，不能外推普通Web的所有工具表现。

取消后的远端消耗可能无法确认，费用无可信价格cost=null。关闭失败则保留未结算/安全阻止，不清锁、不重建资产。必须重新验证冻结和动态资源才能未来Live。
