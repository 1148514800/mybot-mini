# 安全与预算审计

本次范围为离线工程开发；真实模型 API/HTTP 请求0，真实付费 Judge请求0，费用0次新增调用（不对历史费用作判断）。Git fetch/push 和测试中的本地伪HTTP服务不是模型请求。

Codex真实交互yes审核0次，没有触发需Codex输入的审批。离线套件内部使用原有模拟ApprovalDecision/PTY挑战，不把它们伪称为本轮人工审核；没有缓存、预输入yes或变更平台权限。

## 源码审查

- Patch参数验证器与限制未放宽：完整文件SHA256、唯一上下文、路径/敏感目录/符号链接限制、文件大小及操作数限制保持原值。
- 新字段诊断在原验证失败之后计算，最多4条，仅含固定Schema字段、数组位置和固定验证类别；不序列化ValidationError、message、instance、Patch内容、原始键名或路径值。非法额外键不会回显。
- Preview纯输入错误只沿用已有恢复空间。无法解析的JSON无法确认意图，继续停止。正式Write非法参数safe_to_retry=false；元数据提示stop_write_no_replay。stale的既有可恢复标记未扩大，没有任何自动重放。
- 未新增Patch执行器，未更改_preflight/_stage/_publish/_recover、Journal、审批器、命令启动器或Seatbelt。Preview不授予Write权限；提示要求先Preview、变化后重新Preview、成功后保留changes结构。
- 不认可python -c、打印OK、非runner自定义断言；认可runner仍必须有真实批准、启动、完整结束、成功退出、非零测试数、非截断输出、对应Revision及Patch文件哈希。有效证据仍不替代模型合法结束。
- 新测试入口提示来自RuntimeCase.public_test；原加载器固定其为公开unittest argv。命令由模型发起，原TTY/Seatbelt/Controller链未改。通用边界提示无case ID、隐藏断言或解法。
- 失败分类只输出解释，不改Strict、Judge、Controller或历史记录。保留runtime、安全、预算、文件/Journal违规优先级。

## 保护与扫描

开发前对基线576个已跟踪文件逐文件SHA256；除本轮6个实现/入口文件及AI_HANDOFF外，569项基线文件受保护。包括完整历史报告、Canary、Phase25、Benchmark公开与私有资产；这些文件只有哈希核对或原回归使用，没有改写。原13个Attempt运行目录的raw逐项与受保护的历史副本匹配（13/13）。main和全部Tag引用、53个现有ZIP逐项核对；没有生成新Phase、移动Tag或重导出ZIP。

对所有原已跟踪文件和新增代码、最终报告进行凭证特征与禁止路径扫描，并审阅修改内容；不输出可能的密钥值。检查真实config/config.json、.env、.venv、Session/缓存和AppleDouble均未进入提交。启发式扫描不能证明不存在所有形式的秘密，结合最小改动和内容审查；实际计数/哈希核对结果见offline-validation.json。

ExFAT原仓库已有._pack索引警告；没有删除或修改其Git元数据。开发与验证worktree位于APFS，不复制原配置或Session。原main工作区用户修改保留。

## 回归覆盖

新44项契约检查和原1114项全部保留；原取消/中断/晚到响应、真实工具ID配对、每次审批、Seatbelt、Journal/Index、请求预算（含fallback物理请求）及single/failover测试继续执行。首次开发并发修改源码时，原冻结校验拒绝执行，按预期触发frozen_environment_changed；源码稳定后重跑通过，没有跳过断言或放宽冻结。
