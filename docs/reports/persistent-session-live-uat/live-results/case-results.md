# 本次真实Live Case状态

用户授权GRANTED_16_REQUESTS有效，但进程前置检查不通过。三个Case均未启动，不判FAIL/PASS。

| Case | Task Success | Workflow Success | Safety/Integrity | UX | Source Integrity | Active Pin Correctness | Model Request Inclusion | Semantic Adherence | Historical Information Loss |
|---|---|---|---|---|---|---|---|---|---|
| L01 | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | 未测 |
| L02 | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | 未测 |
| L03 | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | 未测 |

每Case Attempt=0，reservation=0，实际HTTP=0。Safety/Integrity这一Case评分为BLOCKED表示未执行Case验收；准备工作完整性检查通过是另一件事，不替代Case成绩。Supersession/Revocation均未执行，不因离线结果改判。
