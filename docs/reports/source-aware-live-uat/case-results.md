# Live case results — not executed

|维度|S01|S02|S03|
|---|---|---|---|
|Task Success|BLOCKED|BLOCKED|BLOCKED|
|Workflow Success|BLOCKED|BLOCKED|BLOCKED|
|Safety/Integrity（Live）|NOT_RUN|NOT_RUN|NOT_RUN|
|UX（真实Case）|NOT_RUN|NOT_RUN|NOT_RUN|
|Active Pin Correctness（Live）|NOT_RUN|NOT_RUN|NOT_RUN|
|Source Preservation（Live）|NOT_RUN|NOT_RUN|NOT_RUN|
|Assistant Echo Influence|UNKNOWN/NOT_RUN|UNKNOWN/NOT_RUN|UNKNOWN/NOT_RUN|
|Decision Classification|NOT_RUN|NOT_RUN|NOT_RUN|
|Token Budget Compliance（Live）|NOT_RUN|NOT_RUN|NOT_RUN|

原因均为NOT_GRANTED；没有创建真实Attempt/Session/Pin，不能用合成通过填充这些格子。离线资产完整性与授权门PASS另行报告，不等于Live Safety已经验收。

MockTransport机制结果：9次模拟SDK发送，S01最终5/5、S02最终3/3、S03最终4/4源单元保留；Pin状态分别为旧superseded/新active、旧superseded/新revoked且active空、两兼容Pin active。真实Semantic Adherence未验证。
