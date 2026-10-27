# AI_HANDOFF

## 当前目标与状态

codex/coding-workflow-canary-v1，基线16f25f74db78089bf1bc697022e53f46473449bd。C01离线实现/验证完成，Implementation/Preregistration与唯一新prepare/freeze/verify均完成。真实Provider授权NOT_GRANTED，DeepSeek/GLM/摘要/JudgeLLM0，旧GRANTED_2_REQUESTS已耗尽不继承。

## 已完成

只增scripts/coding_workflow_canary_v1/与专项，生产AgentLoop/Controller/Authority/Receipt/RunCommand/Session/原UAT不变。新notesearch-mini五公开文件、干净Bug Git基线/无remote；Public5/Host10实际Seatbelt隔离基线fail、Reference pass。只允许notesearch/search.py：原生读取SHA→Preview→Receipt Commit→Journal，额外scope gate拒绝其他路径/argv，不改写参数或伪造工具。Revision Gate核对完整workspace/Git与连续Native Journal/hash链，允许可证明合法Revision，未知漂移HALT，不能reset或再prepare。

原生SDK Mock+headed Chrome固定8903正常闭环：6 Mock请求，Preview/审批可见，SYNTHETIC_APPROVAL一次，实际command macos_readonly测试5通过，Controller verified/Revision1，独立Host10通过；刷新仍6无重放，服务exit0/SDK/Lease/SQLite/端口/Profile自动清理。14机制/功能维度通过，human_command_approval=false、strict_success=false正确保留，synthetic_workflow_pass=true，不是模型能力或真人Live成绩。

完整check_phase及独立补充2142去重unittest PASS，新增45，程序式检查另执行；源码前后hash一致。14组失败情形独立保存，包括未修改/Receipt/范围/审批/测试/过期Revision/协议/预算/Stop。审批等待时Stop原运行时可能保留uncertain/Lease，保留失败和实际Patch，不说回滚。不放宽ownership；新Fixture显式当前GID，避免/private/tmp继承wheel。32k输入/16k工具结果/120k上下文字符在冻结前固定，1800输出预留，不保证部署窗口。

## 下一步与边界

报告docs/reports/coding-workflow-canary-v1/。Implementation d679d21914adc1e8b9a758b2611d1b35d80c4c2c、Preregistration/冻结源码 0807b612e734c212588045107ba33f992adecba0。~/.mybot-mini/uat/coding-workflow-canary-v1-20261027/已唯一prepare/freeze/verify，干净Bug Fixture HEAD 12f2b1df12dffe89f719796c725afb7a481ba4f0，Revision0，两库完整/身份固定且0 Attempt/reservation/HTTP、事件空，固定8903，C01单Attempt/最多12物理请求，工具≤40、写≤2、命令≤2、无进展4、任务600s/命令30s/Web900s，SDK重试0。freeze后不得改源码/Fixture/Host测试/评分。

未来必须新GRANTED_12_REQUESTS及原冻结/当前环境/独立Chrome核验；每次命令另需真实用户在原WebApproval确认，Live operator不代点/不自动批准，拒绝超时无人值守不执行、不重问。不把模型额度当命令批准，不因失败补跑。Host Score在已验证Seatbelt进程运行、绝不宿主import候选，结果不回模型。

原Phase25 Benchmark、R01/D01/D02/T01 FAIL/T02 FAIL/T03 BLOCKED/N01/N02 PASS及旧私库/HALT保留，用户Chrome/8765/真实项目、main/Tag/ZIP/共享AppleDouble不处理。源码332文件完整范围哈希保存（回归Python/依赖325）；最终提交/远程HEAD通过Git确认。
