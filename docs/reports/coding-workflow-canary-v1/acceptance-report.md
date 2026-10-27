# Coding Agent Workflow Canary v1

OFFLINE PASS / LIVE BLOCKED。真实DeepSeek/GLM/摘要/JudgeLLM请求0；没有真实模型能力或真人Live Strict Success结论。

新notesearch-mini干净Bug Git Fixture（无remote），存在大小写/title-only/排序去重/空白查询缺陷。实际Seatbelt隔离基线Public5/Host10均fail，Reference均pass。只允许notesearch/search.py经原生Preview/Receipt Patch改变；其余公开文件、Gold、配置、源码、Git metadata和数据库身份冻结。

Revision Gate在每SDK/HTTP和每工具前后核验：真实Patch成功+有效Receipt、Journal恰好增加修订、唯一文件和after hash/current_matches/原Git基线一致才更新允许状态；保存连续前后hash与Native Journal proof。合法Revision后verify不要求恢复旧字节；未知文件/Git/Journal漂移HALT，不回滚或重做freeze。生产AgentLoop/Controller/Authority/Receipt/RunCommand/SessionEventStore均未改变。

真实headed Chrome固定8903合成闭环PASS：DOM唯一任务→读Public和源码→Preview可见→原生Receipt提交→原命令弹窗→SYNTHETIC_APPROVAL一次→实际Seatbelt测试5项通过→Controller verified/Revision1→独立Host10通过→刷新不重复6次Mock请求/不重复Patch→服务exit0/SDK/Lease/SQLite/端口和Profile自动清理。双Profile Cookie/LocalStorage双向隔离通过，用户Chrome/8765不操作。

15维证据独立：14项机制/业务维度在正常Mock中通过；human_command_approval=false，因为这是SYNTHETIC_APPROVAL。因此synthetic_workflow_pass=true、strict_success=false，两者均原样记录。真实Live需GRANTED_12_REQUESTS以及独立的逐次真人批准，不能代点或伪造授权。

失败专项保留真实失败：无Patch/只预览/错Receipt/SHA/范围、拒绝/超时、测试失败、Patch不测试、测试后Revision2使旧验证过期、JSON不完整/断流、预算、外部Git漂移、unknown/HALT、Restart不重放、刷新和Stop不声称回滚。Stop等待审批时原运行时可能保守保留不确定状态与Lease，不擅自释放或改判成功。初期配置与目录组导致的预冻结演练失败保留日志hash，修复仅在UAT/新Fixture范围，不改生产安全门。

完整check_phase和独立补充通过：2142个去重unittest，新增45项，实际执行2142，重复0。程序式检查已运行，不另伪造数量。源码运行前后hash一致；compileall、JS、diff与真实凭证/保护资产审计见delivery-validation.json。无真实Provider请求，无安装脚本或新依赖。

新唯一prepare/freeze/verify及空库身份最终证据见budget-evidence.json；无需历史额度、不改旧成绩。剩余能力边界见remaining-risks/live-readiness，完整审批与Revision设计分别在approval-boundary/revision-integrity。源码/隐藏测试/评分冻结后不改；最终提交和远程HEAD以交付核对为准。

## 最终冻结

Implementation `d679d21914adc1e8b9a758b2611d1b35d80c4c2c`；Preregistration/冻结源码 `0807b612e734c212588045107ba33f992adecba0`。干净树唯一prepare/freeze/verify已通过；正式Fixture HEAD `12f2b1df12dffe89f719796c725afb7a481ba4f0`、Revision0、无remote、Public/Host源hash固定；332个全类型源码hash匹配，回归325个Python/依赖文件运行前后hash另保存。Provider配置字节/workspace inode/Git metadata/事件库与账本身份核验通过，0 Attempt/reservation/HTTP，事件库空、Lease/8903可用。

原生Web持久最终回复由原Host Coding报告生成，不用模型自述代替完成证据。人工批准维度在本次Mock中明确false；真实C01仍未执行。后续新精确GRANTED_12_REQUESTS只授模型额度，命令批准仍需实际用户逐次确认。冻结后不改源码或Fixture/Gold/评分，不再prepare/freeze。
