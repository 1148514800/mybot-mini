# Real case results

|Case|预算|结果|原因|
|---|---:|---|---|
|R01|1|BLOCKED|NOT_GRANTED；无Attempt、未执行|
|R02|4|BLOCKED|NOT_GRANTED；无Attempt、未执行|
|R03|1|BLOCKED|NOT_GRANTED；无Attempt、未执行|
|R04|2|BLOCKED|NOT_GRANTED；无Attempt、未执行|

每个Case的Protocol Compatibility、Streaming Integrity、Workflow Success、Tool Safety、Steer Queue Correctness、Steer Application、Model Semantic Adherence、UI Responsiveness、Resource Accounting、Cleanup Integrity均为BLOCKED/NOT_RUN，不从Mock结果推导真实PASS。协议、用户可见UX、队列接收、请求包含与模型语义遵从必须分别评分。
