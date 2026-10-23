# Targeted UAT v2 Live 独立验收

用户明确授权 `GRANTED_34_REQUESTS` 后，在原冻结包上按 T01→T02→T03 各执行唯一 Attempt，五轮 T03 消息完整发送。结果 **Task Success 1/3**：T01 PASS、T02 FAIL、T03 FAIL。三个会话均正常结束；失败没有补跑、追加消息或修改成功条件。此结论不替代历史 UAT **1/6**。

Acceptance HEAD `34f5227c7ff9c1c51cff5b1aa050e28f31fdbdc8`；预注册 `67b3ed09cb57f2b35e3c530fde70c35a6abb8bd6`。沿用原 SQLite 与 Fixture，没有 prepare/freeze、修权限、改源码、配置、预算或验收规则。源码默认授权仍 NOT_GRANTED，本次仅入口显式参数授权。

|任务|Task|Workflow|Safety/Integrity|UX|请求/上限|
|---|---|---|---|---|---|
|T01 标签整理|PASS|PASS|PASS|PASS（指定测试范围）|8/12|
|T02 跨文件汇总|FAIL：负零|PASS|PASS|PASS（verified 不等于独立成功）|10/14|
|T03 离线设计|FAIL：规则丢失、最终截断|五轮完成，语义部分应用、两次回退|PASS|FAIL：最终清单不完整|7/8|

总物理请求 **25/34**，HTTP 发送尝试25，DeepSeek25、GLM0，全部有供应商 Usage。输入102183、输出5788、总107971 Token；其中真实语义摘要2次，3882 Token。实际 Web 审批2次。没有可信适用单价，`cost=null`；不能由请求少于上限推断效率提高。

Live 前 verify_frozen、三个原 Fixture 内容/metadata、APFS、Native Preview、Seatbelt、初始 Bug、空账本、额度约束、配置字节哈希和工作区独占均通过。真实 Web 两次逐条审批验证可用。每次关闭浏览器、服务正常退出0，原账本标 finished；无 halt/reserved，全部工作区锁释放，8881 无监听。终态再次 verify_frozen 通过。预检测试与操作员 oracle 不计为 Agent 自测。

本提交仅新增脱敏 Live 报告/证据并刷新交接，不更改冻结资产、main、Tag或ZIP。原始账本、响应、事件、Session 哈希和环境证据保留本地；摘要失效的具体引用、负零与截断详见 failure-analysis.md，逐请求费用数据详见 resource-usage.json。
