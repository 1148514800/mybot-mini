# AI_HANDOFF

## 当前目标与状态

Targeted UAT v2仅离线准备：用户LIVE_AUTHORIZATION明确NOT_GRANTED，真实API/Live Attempt/正式reservation均0。基线92424d080e31cefa2adf3af4c507d8f17a0669c0已本地/远程核对；独立分支codex/targeted-user-uat-v2。新代码与预注册已准备，待本提交后从干净版本冻结；最终Acceptance文档记录确切冻结SHA。生产mybot/、旧scripts/uat/和历史资产未改，不合main、不动Tag/ZIP。

## 新驱动与合同

scripts/uat_v2复用原SQLite schema/FULL事务、BudgetClient、HTTP gate/settlement和原生Web/Agent/Controller/Patch。新限额T01=12、T02=14、T03=8，总34；不转移、不重试旧case，一会话/精确冻结消息，clear/第二会话/失败补发拒绝。默认授权门在凭证读取/SDK/账本修改前拒绝；未来只有用户明确GRANTED_34_REQUESTS才能运行Live。

T01新标签strip/空白/casefold去重/稳定顺序/输入不变；T02新Decimal逐行ROUND_HALF_UP/汇总入口/数量拒bool/固定返回结构；公开README与host-only oracle一致。参考修复只在synthetic模块，模型工作区不含答案。三个正式Fixture位于本机$CODEX_HOME/uat-v2/batch-20261023-targeted-v2，不入Git；只新建APFS目录，原metadata+Preview预检均PASS、初始Bug确认、文件/Index未变。

T03五轮照片设计自然消息，固定input_limit12000，近期1轮，summary_max_chars6000；semantic max_calls=1（每回合）、输出1200、主输出700、fallback deterministic。合成校准前4轮not_needed、第5轮semantic_applied，5主+1摘要，原Session和文件不变，不外推真实摘要质量。

## 验证与边界

原1354全量+旧UAT13+修复专项42=1409已通过；新增v2专项24通过。真实浏览器OFFLINE/SYNTHETIC逐次批准1条Seatbelt只读无网络unittest，原生Receipt提交、revision1、3项Agent测试通过；正式Live审批0/终端yes0。T01/T02真实工具合成闭环及独立断言均通过，仅允许源码改变。

离线跨文件演练曾因合成Client解析已裁剪JSON异常，Controller保守execution_uncertain、停在Preview无提交；已仅修正合成Client从可见完整Receipt字段取值，原测试/产品未改，专项重测通过。真正Live Coding、摘要保真、实际Usage/费用及API认证未验证。

## 下一步与禁止重复

从本次干净Preregistration Commit执行prepare.freeze并验证源/配置/Fixture内容+元数据/账本身份，完成验收报告、Acceptance Commit、Push并核对远程HEAD。本轮只交付OFFLINE READY/BLOCKED，不擅自Live、不重跑旧六例、不使用旧22次余额。若未来明确授权，验证同一冻结包后唯一Attempt执行；源/环境/预算/审批/清理不合规则BLOCKED，不边修生产边跑本批。完整合同/消息/评分与证据在docs/reports/targeted-user-uat-v2/。
