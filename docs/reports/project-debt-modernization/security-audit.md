# 安全与历史保护审查

本轮真实模型 API 请求0；此前 A/B 额度未使用。网络研究只读取官方公开文档；合成模型调用、SDK MockTransport 与127.0.0.1 HTTP/SSE 不是付费供应商请求。实际人工终端 yes/nonce 0次、浏览器审批0次。旧及新自动测试包含原有受控测试审批回调，这些不是实际人工批准，生产审批接口未改。

工作区独立且未复制真实 config/config.json、API Key 或 .env。使用合成凭证。对全部813个原跟踪文件及新增文件进行了文件名/体积/凭证形态扫描，并审核新源码/配置/报告差异；没有禁入文件、超过2MB文件或真实凭证发现。模式唯一命中是原 scripts/check_web_ui.py 的明确 SYNTHETIC_SECRET 测试哨兵。扫描不证明不存在任意格式秘密，人工差异检查与未访问真实配置提供补充边界。

保护基线与上一 Web 验收保护清单交叉核验：1560个历史文件 SHA256 不变，涵盖 Phase 学习资料、旧reports、冻结Evaluation源码（trace观察适配单独审阅）、原13与最近8 Attempt原始资产、ZIP/AppleDouble及原工作区用户修改。main SHA 与全部 Tag refs 未变。没有新Tag/ZIP、没有重跑真实Benchmark、没有把新代码冒充旧阶段。trace仅添加资源观察；Strict评分、judge/grader、Controller、Patch发布器、Receipt一次性能力和审批策略源码保持不变。

进程锁使用规范化工作区路径摘要、私有UID目录、O_NOFOLLOW、文件属主/权限/类型/链接数检查、内核flock。不删除未知锁，不猜PID回收；崩溃由内核释放。不确定清理保留描述符直到进程退出。仅同UID合作式CLI/Web协调，不是恶意同UID进程沙箱；外部编辑器和共享Session路径仍需独立约束。

摘要输入先脱敏已知主备密钥、凭证形态、64位Receipt样式；输出只能引用该脱敏来源，不持久化摘要、不转system、不恢复授权/计划/测试结论。字节限额与JSON结构检查之外，不声称能够验证所有自然语言事实。观察回调失败只记数，不可授权工具。

CLI不再回显SDK异常载荷；Web既有Host/Origin/cookie/CSRF/CSP/受权SSE、nonce审批、MCP owner、Seatbelt和发布停止门保留。遗留基础文件TOCTOU潜在风险、同步IO取消延迟仍列剩余债；本报告不是全项目安全认证。
