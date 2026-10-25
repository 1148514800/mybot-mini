# 真实Case结果

LIVE_AUTHORIZATION: NOT_GRANTED。三个Case均无Attempt，不能以离线或旧UAT代替。

| Case | Task Success | Workflow Success | Safety/Integrity | UX | 原因 |
|---|---|---|---|---|---|
| L01 | BLOCKED | BLOCKED | BLOCKED | BLOCKED | 未授权、未发送真实模型请求 |
| L02 | BLOCKED | BLOCKED | BLOCKED | BLOCKED | 同上 |
| L03 | BLOCKED | BLOCKED | BLOCKED | BLOCKED | 同上 |

Pin来源/有效集合/实际请求包含、真实语义遵从、替换、撤销、真实历史信息损失、真实重启继续均未评分。预算与ASGI MockTransport离线预检另列，不混入本表。无真实浏览器Live截图。
