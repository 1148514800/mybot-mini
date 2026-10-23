# 安全与完整性审计

LIVE_AUTHORIZATION: NOT_GRANTED。真实供应商请求、正式账本reservation、Live审批均0；不使用旧剩余额度。只新增scripts/uat_v2与独立专项/报告，生产mybot/、旧scripts/uat/、旧测试/Judge、历史报告、main/Tag/ZIP均不修改。

新Fixture位于独立APFS私有目录；新建根在写子文件前设当前EGID，原UID/GID/ACL/xattr/mode检查及原生dry_run Preview实际通过，不削弱安全策略，不chmod777、不删除安全元数据。预检前后全文件/Git fingerprint一致，初始公开与独立断言均确认失败；正式Fixture不使用演练修复后的目录。

原SQLite schema、FULL同步、HTTP gate、BudgetClient和settlement复用；v2仅替换case/global限额，独立文件及plan hash隔离，重启不归零，不转移额度。每Case一会话、精确冻结消息、禁止clear/第二会话/失败后补发，SDK重试不为0则拒绝。Primary/Backup/摘要/失败都占额度；重复HTTP、鉴权、证据写入失败和清理不确定停批。

真实浏览器仅在OFFLINE/SYNTHETIC可丢弃演练中逐次批准1条unittest，已核对argv、cwd、30秒、Seatbelt只读/无网络；没有自动批准Live、终端yes、缓存许可或nonce复用。截图选择最终状态，不公开含主机Python路径的审批详情、不公开nonce/Receipt。合成闭环原生工具成功不当作Live成功。

隐藏oracle和合成参考修复只存在主机侧驱动，不复制到模型工作区、用户消息或工具结果；独立断言不补算Agent测试。完整私有响应/视图只写本机权限受控目录；未来活动日志存已经脱敏的事件，避免128条UI窗口丢失早期证据。公开报告仅状态/计数/脱敏预检/截图/哈希。

开发时跨文件合成Client因当前4000字符裁剪后的metadata不是完整JSON而抛异常，Controller保守报告execution_uncertain；该次停在Preview后，未提交T02文件。确认完整Receipt仍在可见消息后只修正合成解析器；没有从隐藏主机状态取Token或修改产品裁剪逻辑。新增闭环断言保留并重测通过。此为离线驱动开发证据，不是真实模型Attempt或生产阻塞缺陷。

最终冻结/回归/历史资产哈希与Git提交信息见Acceptance Commit内的offline-validation.json、freeze-summary.json和evidence-sha256.json。实际API认证、真实模型Coding及摘要质量仍NOT_VERIFIED。
