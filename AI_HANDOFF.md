# AI_HANDOFF

## 当前目标与状态

Targeted UAT v2 Live已在用户明确授权GRANTED_34_REQUESTS后完成，三个Case各唯一Attempt，T03五轮冻结消息完整。Task Success为1/3：T01 PASS、T02 FAIL、T03 FAIL。独立分支codex/targeted-user-uat-v2，Acceptance HEAD 34f5227c7ff9c1c51cff5b1aa050e28f31fdbdc8，预注册67b3ed09cb57f2b35e3c530fde70c35a6abb8bd6。未重新prepare/freeze，未改生产代码、测试驱动、合同、配置、Fixture或额度；源码默认NOT_GRANTED保持原样。

## 已完成与实际结果

T01原生源码调查→Preview/Receipt→Commit→Agent unittest3项通过，Revision1 verified，公开与独立验收PASS，仅tag_shelf.py改变。

T02两模块真实修改、service调用line_subtotal，Preview/Receipt Commit成功，Agent unittest4项通过，Revision1 verified；独立验收在零数量负单价处失败：-0.00应为0.00。首次断言失败后其余独立断言未执行，不能算通过。Workflow与Safety通过，Task失败。

T03真实摘要2次：第3轮semantic_applied_pruned，第4轮精确引用失效后fallback_invalid_or_failed_response，第5轮fallback_token_budget（无新增摘要HTTP）。最终主回复finish_reason=length、700输出Token，已定字典序规则丢失，明确未知与未实现清单截断。早期5限制、最新批量重命名限制、目标及三职责保留；无虚构实现、测试或照片修改。原Session5轮用户SHA完整、配对合法，无摘要写回或文件副作用。

## 资源、验证与证据

原SQLite总25/34物理请求，T01=8/12、T02=10/14、T03=7/8；DeepSeek25、GLM0，HTTP发送尝试25、失败请求0、Usage缺失0。输入102183、输出5788、总107971 Token；摘要2次3882 Token。真实Web逐次审批2次，均只读无网络Seatbelt unittest；无自动yes。cost=null，无可信适用单价，剩余9次不授权补跑。

Live前后verify_frozen通过，APFS/原metadata/Preview/Seatbelt/初始Bug/空账本/工作区锁均核对。三个服务正常退出0，case finished，无reserved/halt，锁释放、8881无监听。公开与独立oracle仅作为操作员Task验证，不补算Agent测试。Live结果失败如实保留；历史UAT 1/6不改。原离线1409+新增24测试结论只代表此前离线验证。

新增脱敏报告/证据在docs/reports/targeted-user-uat-v2/live-results/，含逐请求Usage、四轴评分、语义逐轮状态、审批、失败分析和SHA256。原始响应/事件/环境/Session哈希及账本保留本机原冻结包；不提交私有配置、Receipt、nonce或完整原始对话。本阶段仅报告与交接变更，不合main、不动Tag/ZIP；完成报告一致性/脱敏/冻结检查后提交并按用户授权Push同一分支。

## 下一步与禁止重复

本批已关闭，不重启Case、不补消息、不用剩余额度、不修冻结Fixture或事后修改条件。后续只能另起明确修复任务处理Decimal负零、摘要引用诊断/规则保留、输入门与输出长度协同及截断UX；新Live必须重新预注册冻结授权。当前没有实施这些修复。不要把Controller verified或语义一次应用替代独立端到端成功。
