# 安全与隐私审计

结果：OFFLINE PASS。Implementation：`cd8f856e885d677daa89a38e71539cb638f513e0`。自动检查是辅助，已人工审查完整源码 diff、原发布路径和测试断言；没有第二个写入器。

| 边界 | 检查与证据 |
|---|---|
| 原子性/恢复 | 原 _preflight/_stage/_publish/_recover 保留；多文件冲突零部分提交；故障注入恢复原文；并发发布冲突保留 execution_uncertain；原 61 项 Patch 与 101 项 Git workflow 回归通过 |
| Journal 归属 | Preview 不建立 entries；成功发布才记录最终 SHA；失效 Journal 安全拒绝；没有修改 Git index 的新路径 |
| 文件/路径 | 完整哈希、inode、mtime/ctime、mode/属性和父目录身份绑定；相同字节的新 inode/版本拒绝；symlink、逃逸、敏感路径、新增已存在均拒绝 |
| 生命周期/预算 | turn finally、Session clear、取消、超时、失败消费、TTL、重启、跨实例/Workspace；原批次 Write gate 和 deadline fence，无自动重放 |
| 测试证据 | Preview revision 0，成功 Commit revision 1；必须当前哈希 + 审批后非零 unittest/pytest；python -c 冒充失败 |
| 审批/Seatbelt | 原 RunCommandTool 与权限提供者不变；真实 Seatbelt 临时 fixture 测试；模拟批准仅限离线测试；实际操作员 yes/nonce 为 0 |
| 凭证/能力 | secrets 256-bit opaque；只在当前模型工具结果传递；快照只在内存，Token 只存 SHA；Trace 白名单无 Token/正文；Session 写盘前脱敏 |
| 历史 | 1034 文件 SHA 校验无变化：原 13 例 raw、最近 8 例 raw、历史报告/Phase、53 ZIP/AppleDouble；main 与 26 Tag 不变 |

检查了全部 781 个原有 tracked 文件及新增源码；无真实 config/config.json、.env、.venv、Session、缓存、AppleDouble 或不必要大文件进入提交。高置信度密钥模式扫描 0 命中；这不能证明任意文本绝无秘密，因此结合逐文件 diff 审查、使用合成凭证和不接触真实配置。报告只保留计数/哈希，不复制原始 SDK 错误、命令 stdout、原 Patch 参数或 Receipt。详见 [history-integrity.json](history-integrity.json)。

不确定性保持原语义：单文件 POSIX 发布，多文件回滚非崩溃事务；无法抵御所有恶意并发竞争，不承诺文件系统未报告的版本变化。TTL 到期是逻辑失效，不创建后台线程；在下次访问/结束时释放那一份有界内存。默认 Legacy 的接口与审批停止门保留。本轮真实模型 HTTP 0，没有使用旧轮剩余 68 次额度，也没有读取后上传真实 API Key。
