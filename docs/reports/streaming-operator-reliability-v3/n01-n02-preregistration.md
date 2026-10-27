# 新双Case Canary预注册

LIVE_AUTHORIZATION: NOT_GRANTED

未来仅新精确GRANTED_2_REQUESTS有效，旧v2已消耗3次及剩余3次均不继承。基线e9d04f2c28fb46c0216df362170beaeaeccd452d，分支codex/streaming-operator-reliability-v3。新批次streaming-steer-recovery-canary-v3；唯一目录~/.mybot-mini/uat/streaming-steer-recovery-v3-20261027/，端口固定127.0.0.1:8902。新独立workspace、事件SQLite、请求SQLite，不能替换或覆盖原资产。

| Case | 固定用户原文 | 操作 | 请求上限 |
|---|---|---|---:|
| N01 | 请用四句话简要解释Python列表推导式，不调用工具。 | 首个真实非终态Chunk交付后，Chrome提交“请改为英文回答。” | 1 |
| N02 | 请用较长的中文Markdown说明介绍一个完全离线的文档检索工具，分多个章节详细说明输入、索引、查询、结果展示、错误处理及使用限制，不调用工具，不修改文件。 | 首个真实非终态Chunk交付后，Chrome Stop | 1 |

严格N01→N02、每Case一次Attempt，总共2次物理请求，包括主备/失败/HTTP发送；不转移、不重试、不补跑。主coco/deepseek-v4.1-flash，备coco2/glm-5.3-flash，SDK retries=0，stream=True/include_usage=True。预算先持久reservation、HTTP前原持久计数；首请求失败后的备用请求也受本Case 1次上限约束。工具Registry空、MCP/Skills/Coding/模型摘要/Judge关闭。估算输入上限14000、输出预留1200、timeout90、max_react_steps4，均沿用受控策略。

各Case首真实SDK流在真实首个非终态Chunk yield且消费者恢复迭代后设置8秒屏障；原对象与顺序不变，不生成Token/工具，不改已发送请求；实际等待单独计时，不冒充自然Provider延迟。首块已终态或操作窗口错过，记INCONCLUSIVE，不重跑。

N01：真实queued→无下一步骤时not_applied；在途请求hash不变；不得自动发送下一模型请求；UI显示未生效和显式填入下一轮入口；只读刷新/SSE重连后账本计数不增加。queued/applied/HTTP/response/语义分开，不能称在途回复已切英文。N02：真实Stop时序、SDK close、不可信部分不标complete、无工具/重试/透明Fallback；不可靠Usage为null；native Session、SQLite、wait exit0、无Listener/Lease、Chrome/profile自动清理分别核验。

异常协议/权限/预算/持久化/清理不确定立即HALT，不继续；HALT不阻止清理自己资源，不清HALT制造成功。普通格式/语义失败如无安全阻断按原合同记录后继续。无可信部署价格cost=null。只发布有界诊断/来源ID/hash/脱敏截图，不发布完整模型请求/回复/chunk、参数、密钥、Cookie/CSRF/nonce、私有库或profile。

离线完成实现与全部验证→Implementation Commit→本预注册Commit→干净工作树唯一prepare/freeze/verify→Acceptance Commit→Push/远程HEAD核对→再次verify。freeze后不改源码。命令：`uv run python -m scripts.streaming_steer_recovery_v3.prepare prepare --provider-config <原本地配置路径> --browser-evidence <本轮隔离证据>`；freeze与verify同模块对应action。prepare只读配置字节/模型元数据，不创建SDK或连接供应商。

未来Live：先原冻结verify，再核对进程/端口/Lease/两库/空账本/新隔离浏览器；`uv run --no-project --with playwright python -m scripts.streaming_steer_recovery_v3.browser --chrome <本机Chrome> --output <新私有输出目录> --live --authorization GRANTED_2_REQUESTS`。原生入口create_app→ChatRuntime→AgentLoop→ProviderFailover→SDK，只由DOM发消息/Steer/Stop。真实结果另建live-results/execution-01，不改本离线报告。成功也不自动继续T01或Steer其他样本。
