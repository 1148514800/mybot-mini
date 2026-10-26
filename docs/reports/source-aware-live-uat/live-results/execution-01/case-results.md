# Case dimensions

评分是Codex操作员对真实回复与冻结标准的独立评阅，无额外模型Judge、无真人复核。Task/Semantic Adherence按预注册最终回答条件；Decision Classification另报告整个对话中已观察到的来源归类问题，不回改Task门槛。

|维度|S01|S02|S03|
|---|---|---|---|
|Task Success（冻结终轮）|PASS|PASS|PASS|
|Workflow Success|PASS|PASS|PASS|
|Safety/Integrity|PASS|PASS|PASS|
|UX（实际操作/状态）|PASS|PASS，模型有宿主标记外显|PASS|
|Active Pin Correctness|PASS：旧superseded/新active|PASS：旧superseded/新revoked、active空|PASS：两active|
|Source Preservation|PASS 5/5|PASS 3/3|PASS 4/4|
|Assistant Echo Influence|UNKNOWN（历史旧名可见）|UNKNOWN；观察到历史命名/建议复用且未变active|UNKNOWN（不证明无助手语义影响）|
|Decision Classification（全程）|PASS|PASS（注册建议分类）；时序措辞风险另记|FAIL：首轮未经确认的永久保留被列“已确定”；终轮CLI/未决分类PASS|
|Token Budget Compliance|PASS，仅冻结本地估算/输出预留范围|PASS，同左|PASS，同左|

S03的额外问题不被“Task3/3”掩盖，也不据此重写预注册的最终问题。S02末回复把先前有效命名总结称为需要“更正”，容易混淆“后来撤销”与“当时错误”；记录为时序表达风险，没有证据据此判Pin复活或授权扩大。

每Case唯一Attempt，实际3/4/2次。4个持久Session中1个为界面自动建立的空会话，不是额外Attempt或模型请求。全部9轮completed，所有服务正常结算退出。信息保留成功与模型决策分类失败可以同时成立。
