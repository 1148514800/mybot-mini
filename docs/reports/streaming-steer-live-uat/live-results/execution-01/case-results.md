# Independent case results

|Dimension|R01|R02|R03|R04|
|---|---|---|---|---|
|Protocol Compatibility|FAIL：实际可流式发送/收块，但未可信完成|BLOCKED|BLOCKED|BLOCKED|
|Streaming Integrity|FAIL：eof=false，可信终态缺失|BLOCKED|BLOCKED|BLOCKED|
|Workflow Success|FAIL：provider_error|BLOCKED|BLOCKED|BLOCKED|
|Tool Safety|PASS：0 tools，无读取/写入|BLOCKED|BLOCKED|BLOCKED|
|Steer Queue Correctness|N/A：未计划Steer|BLOCKED|BLOCKED|BLOCKED|
|Steer Application|N/A|BLOCKED|BLOCKED|BLOCKED|
|Model Semantic Adherence|UNKNOWN：预览内容符合五段主题，但没有可信完整回复|BLOCKED|BLOCKED|BLOCKED|
|UI Responsiveness|PASS（局部）：终态前可见真实文本；最终错误保留|BLOCKED|BLOCKED|BLOCKED|
|Resource Accounting|PASS（本地请求计数），供应商Token UNKNOWN|BLOCKED|BLOCKED|BLOCKED|
|Cleanup Integrity|FAIL：正常关闭等待超时；最终端口/锁/进程资源已释放|BLOCKED|BLOCKED|BLOCKED|
|Overall|FAIL|BLOCKED / 未Attempt|BLOCKED / 未Attempt|BLOCKED / 未Attempt|

唯一R01 Attempt在原账本仍running；其唯一物理reservation已failed并结算，没有保留的模型执行。账本HALT禁止继续，不能手动finish/清HALT制造完成。三组未执行不可据离线或历史结果评分PASS。

持久化assistant文本带宿主[OUTPUT]未完成告警；去掉该公开固定告警后的正文哈希与SDK组装文本一致（见stream-timing.json），这只证明正文对应，不证明完整。未把模型自由文本当可信完整任务成功。
