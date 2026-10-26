# Source-Aware semantic Live UAT — executed

本轮在明确GRANTED_10_REQUESTS后一次完成S01→S02→S03，冻结最终Task标准3/3 PASS，原user来源单元12/12保留。**不是所有行为都无缺陷**：S03首轮把“原始笔记永久保留”列作已确定要求，属于未确认推断强化；全程Decision Classification记录FAIL。助手语义影响没有被证明清除。

输入HEAD `339da9b0aeaf02a0b4a4226e55fbf80ecd7a6f57`；Preregistration `ce3a44dbfdb0fef5662753501ca8a021a0be55f8`；分支codex/source-aware-live-uat。复用唯一原新批次、原Provider、workspace与两库；没有prepare/freeze、改源码/提示/评分或补跑。旧OFFLINE报告和更早Live结果原样保留。

|Case|冻结最终Task|Workflow|Source Preservation|实际请求|
|---|---|---|---|---:|
|S01 照片|PASS|PASS|5/5|3/4|
|S02 音乐|PASS|PASS|3/3|4/4|
|S03 笔记|PASS|PASS|4/4（含可选/未决状态）|2/2|

S01采用assets.jsonl，photos.jsonl仅作为历史，五项独立要求完整复述。S02新Pin替换后有效、撤销后active空；最终准确回顾tracks.csv/library.csv为历史，三项用户要求与两条助手建议清楚区分。S03终轮正确保留两约束、未认定同类冲突、CLI可选、全文搜索未决。

来源保留由实际SDK observer+真实Source ID/Session/user/span核验，并独立以SQLite原文和实际SDK消息哈希复核；不把助手复述或答案正确当成user来源保留。无关来源丢失0、预算历史省略0、协议回退0、映射失败0；局部失效Pin跨度遮蔽仍明确标incomplete。两类照片/音乐独立要求共8/8；含笔记两约束、建议及未决状态合计12/12。

**助手影响仍存在可见通道。** S02末请求中两个旧命名仅见于保留的低信任助手历史；三条助手消息的实际SDK哈希均验证保留。最终把这些名字用作历史而非有效Pin，没有把秒数列/错误展示建议变成用户决定。没有发生精确整句命中省略（0条），不代表语义复述已经清除；残余与因果影响仍UNKNOWN。

实际9/10次物理模型请求，DeepSeek9、GLM0、模型摘要0、失败0、Judge0，模型HTTP发送9。供应商输入13,797、输出1,774、总15,571 Token；Usage完整且与原ledger/private usage双份一致。cost=null，无可信部署价格。估算输入4276–9773（上限14000），参考增量最大1891估算Token，输出预留1800；所有finish_reason=stop，未输出截断。未知部署窗口仍未知。

新headed Chrome profile与动态双profile Cookie/LocalStorage隔离验证通过，全部消息/Pin创建替换撤销经真实页面确认。三个自己的服务exit0、端口释放、lease释放，profile清理。冻结verify通过、9 completed turns/0 tools、workspace字节不变，无凭证/权限/计数异常、文件污染或不确定执行。残留旧8765 launcher未被触碰；它本轮无监听，不对更早用户内存会话作保留保证。

本结果只覆盖一次冻结样本和配置，不能由Source Preservation推论所有语义/建议分类正确。未使用余下1次，不补跑。完整维度与额外问题见case-results、semantic-adherence、assistant-echo-analysis；报告提交/远程HEAD在交付回复核对。
