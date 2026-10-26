# Security audit

未获得新Live授权，入口首先检查精确GRANTED_8_REQUESTS，再读取配置/DB或构造SDK。授权拒绝测试验证无Provider/verify/SDK访问；旧16/10次授权、尾空格与布尔值均不接受。本轮0真实请求，所有SDK发送测试都使用MockTransport。

新批次、workspace与两个DB独立；新Fixture公开且只读。写入、命令、MCP和Skills关闭，原Tool Authority、审批、Pin/决定来源及生产Cookie/CSRF/CSP/Origin未改。UAT进程只在自身lifespan内收紧Registry，退出还原，不替换Loop或原生读取工具，不改模型块。8秒时序屏障提前冻结，角色块不计可见Token。

持久Ledger在发送前reservation，HTTP钩子仅允许一次，流消费/关闭后才结算；未知HTTP状态保守占额度。重复Attempt、跨Case借额、并发未结算、inode替换、隐藏retry、意外摘要、401/403和清理失败阻止继续。取消真实远端账单将UNKNOWN，不能记Usage0。

原Provider文件仅本地读取，验证字节/模型/凭证存在及端点指纹，远端合法性UNVERIFIED；未复制凭证或修改原配置。只提交脱敏哈希/空计数/公开Fixture与探针截图，未提交SQLite、Cookie、CSRF、nonce、完整SDK Prompt、响应或profile。

代码和Git历史检查显示mybot、生产依赖、旧UAT脚本、旧Live结果与冻结资产未改，未创建/移动历史Tag或ZIP。未结束用户服务或未知进程；独立8899在准备时空闲、Lease可获取释放，Live前仍须动态重检。检查字段见budget-evidence.json。
