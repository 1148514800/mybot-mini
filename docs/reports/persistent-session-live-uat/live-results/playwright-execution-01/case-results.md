# Frozen rubric results

评分由Codex操作员在请求完成后独立检查真实回复、SQLite来源及冻结SDK观察证据；未调用额外模型Judge，也没有真人复核。本表PASS仅指冻结条件；产品瑕疵与信息损失单列，不能用“Pin进入请求”替代语义评分。

|维度|L01|L02|L03|
|---|---|---|---|
|Task Success|PASS：两核心边界、四类未决项保持|PASS：新命名/撤销后历史区分正确|PASS：新回复准确继续原讨论|
|Workflow Success|PASS：9条原文、真实页面两次确认|PASS：4条原文、替换/409/撤销|PASS：真实进程退出、重启、原会话继续|
|Safety/Integrity|PASS|PASS|PASS|
|UX|PASS，有needs_review歧义|PASS，生命周期措辞有误导|PASS，历史无旧验证提示正确|
|Source Integrity|PASS：原user/span仍在SQLite|PASS：两原user/span可验证|PASS：重启来源保持|
|Active Pin Correctness|PASS：两active|PASS：superseded→active→revoked|PASS：两active恢复|
|Model Request Inclusion|PASS：请求2–9均两Pin|PASS：第三仅新，第四无Pin|PASS：请求14两Pin|
|Semantic Adherence|PASS，附质量限制|PASS，附生命周期措辞限制|PASS，附needs_review解释限制|
|Supersession Correctness|不适用|PASS：旧superseded/新active、stale409|不适用|
|Revocation Correctness|不适用|PASS：新revoked、请求无active命名|不适用|
|Historical Information Loss|存在压缩/省略；未枚举全部事实|FAIL（信息保留指标）：3/累计5原用户单元来源被去除；不是Safety FAIL|存在压缩/省略；核心Pin保留|

L01=9/10、L02=4/4、L03=1/2，均一次Attempt，无重试。模型语义未出现冻结标准规定的FAIL；信息保留指标的失败完整保留，没有改判为无损，也没有追加提问追求更好结果。新会话UI自动建立的一个空会话留在独立事件库，合计3 sessions，不是额外Attempt或模型请求。
