# AI_HANDOFF

当前任务：真实用户Web端到端UAT；基线e3bfc897363b766c5cfacba62f571a26657898f4，分支codex/real-user-task-uat。产品mybot/、依赖与历史资产未改。原工作区用户修改保留。

Live前已完成六组指定专项、13项UAT硬预算/Fixture/生命周期校验、compileall、diff检查及真实浏览器无模型连接预检。U03公开基线通过；U04/U05公开和独立验收基线失败，修复oracle自测在其他离线目录验证有效。U06冻结输入18000、输出512、summary1200，合成触发校准5/6轮，绝不计作Live成功。

新增scripts/uat仅用于本次验收：SQLite持久化全局48与逐案例2/4/6/14/14/8预发送reservation，SDK/HTTP双门覆盖主备、取消和摘要；无重跑、无重置、无Smoke/Benchmark。Fixture、独立oracle和最终消息/评分条件在本冻结提交。Live后只读评分与写报告，不改产品或测试代码。

实际批次数据留在/tmp/mybot-uat/batch-20261022，真实配置只在内存读取原本地文件；不可提交Key、有效Receipt/nonce或完整私有对话。报告目录docs/reports/real-user-task-uat。尚未开始真实模型调用；接下来按U01..U06依次操作真实浏览器，并逐字审核安全unittest审批。鉴权/预算/执行或清理不确定/保护资产异常立即停整批。测试不以全PASS为目标；失败保留分母不补跑。
