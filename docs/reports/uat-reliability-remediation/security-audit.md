# 安全审计

本轮只授权离线：全部新增模型行为为合成Client；旧Provider测试使用MockTransport/本地测试Server。真实DeepSeek/GLM/摘要API请求均0，付费Judge0，不读取生产Key用于运行，不使用历史剩余22次请求。不修改历史Fixture、Judge、Strict评分、旧报告、Tag、ZIP、main或主工作区用户两文件。

源码审查重点：check_metadata及ACL/xattr/UID/GID条件未动；文件路径/anchor/hash/version、Receipt作用域和单次使用、Journal发布/回滚、Seatbelt、命令审批、Controller verified条件未动。诊断只输出固定值，不传原异常、Patch正文、Receipt/nonce或任意绝对路径。成功Preview仍按既有安全机制展示有界Diff，不等同Commit；测试退出0不等同整个任务成功。MCP不复用本地路径展示。

初轮全量发现新增诊断覆盖旧safe_to_retry导致7项兼容失败；已改为仅透传原值并通过61项原Patch专项，原断言未改。最终旧UAT离线校准还发现长度/条数耦合过紧，已将两者分别按空间约束，原13项重测通过；新增成功Commit无失败建议专项，防止观测误报。该问题及重测如实保留在验收说明，不能把最初失败算通过。

新增v2只在不存在的新根目录设当前EGID；不chmod777、不删除不支持元数据、不更改产品属组校验。预检只有dry_run；实际正式写入仍走原Receipt/Controller。真实浏览器中失败任务显示failed与revision0，未伪造成功。

提交前检查所有跟踪文件的路径/大小和可疑凭证内容，逐项审阅本轮diff；不提交真实配置、.env、.venv、Session、缓存、临时文件或原始完整会话。历史资产与基线比较必须无改动，878个跟踪文件完成路径/大小/内容扫描，545个基线Phase/报告/评测/fixture资产逐字节一致；唯一凭证模式命中为原有Web测试的合成异常字符串。结果见offline-validation.json。

ExFAT的若干._pack*.idx被确认AppleDouble魔数后移到本机临时备份，保留可恢复副本；未移动实际Git pack/index，消除了读取历史时的伪索引告警。没有危险reset/clean/force-push操作。
