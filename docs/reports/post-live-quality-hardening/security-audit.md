# 安全与完整性审计

本轮真实模型授权0；DeepSeek、GLM、真实语义摘要均0。不使用旧剩余9次额度，不重跑旧Live任务。浏览器仅连接临时loopback合成服务；Client没有SDK或供应商网络实现。原产品回归中的模型HTTP均为MockTransport，MCP网络仅为测试用本机服务。

生产改动限于输出/上下文状态、精确摘要保留策略、紧凑合同提示与展示。原命令解析、审批能力、Seatbelt、Patch Receipt、Revision校验、工作区锁、MCP权限、Provider Failover和预算闸门未放宽。截断响应含tool_calls时不执行；绝不自动继续请求。未知文本结束状态不冒充完整交付。

活动与资源字段只加入枚举、布尔、数量、原因类别和覆盖类别，不加入摘要正文或私有模型响应。部分回答走原聊天脱敏函数；Web Coding只显示白名单Host报告。精确引用在脱敏后同时检查来源节选与原始来源，拒绝拼接标记、角色越权和假完成。历史引用从不恢复审批、Receipt、测试或工具权限。

检查全部已跟踪与本轮新增文件，未发现真实配置、.env、.venv、真实Session、AppleDouble、大型文件或实际私有凭证值。新报告不含主机绝对路径、原始私有响应、Receipt或nonce；截图均为合成数据。已知合成key是显式测试假值。完整私有Live响应和配置未复制进仓库。

历史scripts/uat、scripts/uat_v2、v2公开报告、Phase档案未改。原始Live的47项SHA256清单（含原账本、prepared/freeze、响应与事件）只读核对一致；基线原worktree仍58725ca。未执行Tag、ZIP、归档、main合并或历史重写操作。

旧合成协议桩只补充stop/tool_calls字段；对受影响文件的47条原assert以及原有函数AST逐一核对，去除新增finish_reason元数据后完全一致。check_phase只新增本轮专项入口；没有删除旧测试、跳过失败断言或修改成功条件。完整回归结果另见offline-validation.json。
