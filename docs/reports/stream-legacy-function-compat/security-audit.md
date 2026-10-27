# Security boundary

本轮真实模型授权0；旧D01 GRANTED_1_REQUEST已耗尽且不延续。所有SDK与浏览器验收使用MockTransport，不连接DeepSeek/GLM/摘要/Judge。新D02只做离线准备，必须未来新用户精确授权才能运行。

生产只改空legacy字段判定和安全诊断及Web码识别；不移除legacy检查、不执行/转换弃用函数调用、不扩展Registry、MCP、Skills、Coding、审批或Receipt权限。无System权限提升、认证/CSRF/CSP修改。Failover/计数/Token与输出预留/Steer/存储和决定来源语义保持。

旧R01/D01私有账本、旧冻结和原回复未打开；全部旧报告、Tag、ZIP、main保持。新批次独立workspace、两库和请求账本；相同账户仅本地读取原Provider配置做字节指纹与模型存在校验，不复制凭证或请求Provider。

公开证据只含结构、哈希、计数及合成截图，不提交真实配置/SQLite/Profile/Cookie/CSRF/密钥/完整模型Prompt。日志和探针原始JSON只有显式Synthetic数据；真实Legacy字段原内容未恢复。只清理本次创建的Chrome/服务/profile，不删锁、不强杀，不操作用户工作区或旧8765。
