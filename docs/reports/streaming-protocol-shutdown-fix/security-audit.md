# Security audit

LIVE_AUTHORIZATION: NOT_GRANTED。真实DeepSeek/GLM/语义摘要/Judge均0。所有新合成SDK使用MockTransport，base_url为mock.invalid，无真实配置读取；旧回归也只使用其原Mock/本地fixture。没有连接真实模型端点、运行旧Live server、使用剩余额度或重freeze。

原UAT scripts、旧Live报告/评分、旧prepared/freeze与原两库保留。只读核对旧账本仍1请求、R01 running与protocol_or_runtime_failure HALT，前后原文件hash一致，禁止清HALT、伪造finished、重建数据库。新源码与旧freeze不一致是预期，不能更新freeze规避。

普通SSE只增加固定错误代码，不发送完整结构ring、工具参数、完整模型Prompt或SDK异常。敏感文本缓冲、Cookie、CSRF、Origin、CSP、审批、Tool Authority、Pin/Decision权限边界保持。SDK记录仅有8块固定结构元数据；未知finish映射unknown。

SIGINT只作用于本轮启动且核验PID/UID/PPID/出生时间/argv/cwd/监听端口的自身服务；不使用pkill/kill-9，不删除锁或结束8765/用户Chrome。TTY失败复现中的独立fixture也已退出，最终profile清理。无法匹配身份时拒绝发信号。

MCP退出保持进入时的同一Task；cooperative清理超时保持cleanup_uncertain并阻止继续。不存在以HALT“修复”来宣称旧清理成功；模拟HALT的数据仅在新私有临时目录。真实用户数据/私有SQLite、Cookie/Profile、Receipt/nonce、密钥、Prompt/模型原始响应不提交。
