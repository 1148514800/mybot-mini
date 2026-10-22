# AI_HANDOFF

## 当前任务

独立codex/request-budget-full-batch分支，基线3ccd2df。目标：请求效率提示、复用v4的13槽Batch、受控回退、离线回归、授权Live和统一证据报告。不是Phase26，不改旧Canary/Phase25结果。

## 实现

Controller仅精简运行时提示：有效当前Revision证据优先最终回复，最后请求如实决定必要操作；不自动verified、不扩预算。保持原Patch、审批、Seatbelt与Judge。
新Batch固定12自然+1受控槽，204物理上限，单例12/16/20/12。顺序复用v4，先持久预算reservation再SDK，outcome与v4报告交叉审计；既存目录禁止重放。异常/清理不确定立即停止。
受控首次主接口连接故障不发HTTP但占物理、Controller及Batch预算；备用原机制独立Key/Model且sticky，不重放工具。默认none。
文档docs/request-budget-full-batch.md。新增18+25测试，所有原1071保留。

## 验证进度

效率18、Batch25、原Failover50、生命周期42、CLI17、smoke13专项已通过。全量1114项/31套件通过，零跳过（原1071+新增43）；编译、diff与281项历史资产保护检查通过。Live尚未执行；本提交冻结implementation，随后只在干净源码运行授权批次。

## 授权与边界

本轮最多固定13个新Attempt、204物理接口尝试（自然192+受控12，含1合成注入），不是金额上限。用户已授权逐次安全TTY挑战、费用和最终独立分支Push，不需逐例询问。失败不重跑；不作额外Smoke或越权操作。
忽略配置副本0600，不能打印或提交Key。历史、两个Canary、main、Tag/ZIP和主工作区用户修改保留。旧ExFAT ._pack索引警告不清理。
