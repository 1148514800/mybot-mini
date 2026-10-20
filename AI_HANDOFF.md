# AI_HANDOFF

## 当前目标

Phase25在codex/phase-25从ff10fb6独立开发：固定版本12例×3轮、可靠恢复/统计、独立外部Python项目验证及归档。不Push/Merge，保留main两处用户修改、Phase24全部报告/Tag/ZIP和配置。

## 已完成与待验证

新增coding_campaign.py、evaluate_coding_campaign.py及专项测试，复用原evaluate/Loop/Controller/审批/Seatbelt/Judge，不改评分和安全语义；独占started/raw/finished记录和SHA，状态不确定不重放；显式冻结白名单不存凭证。外部入口evaluate_external_coding.py用于固定python-json-pointer的独立URI fragment功能，不安装项目脚本。

Phase24实际历史20次Live、9/12完整成功、Hard4/4；error-retry在ff10fb6已verified/hidden_pass，原文档未复测描述已失效。原归档仍是3f53b05，不含后续修复。

## 离线验证

原916+新增24=940项、25套件全部通过，编译通过；原Phase1/2断言、安全审批/Seatbelt/Patch/Revision/Journal测试保持通过。日志/tmp/phase25-full.log。

## 下一步

完成全部离线回归后冻结Harness Commit，执行一次离线Dry Run，再创建36槽Live Cohort（优先三例未测），同一冻结版本分三轮执行；逐条审核真实PTY审批，不自动重跑。完成后分析、外部任务、脱敏证据清单、文档及独立归档/还原验证。检查点与运行进度保存在忽略的runs目录，完成证据将脱敏纳入文档归档。
