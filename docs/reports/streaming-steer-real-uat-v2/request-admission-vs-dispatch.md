# Admission is not dispatch or comprehension

|阶段|直接证据|不能推出|
|---|---|---|
|Web queued|DOM POST200、Turn匹配、持久user事件|已改变在途模型|
|Native admitted|原on_dispatch触发resolve(applied)事件与宿主monotonic|已获UAT reservation或已HTTP|
|Durable reserved|SQLite事务提交的reservation|发送成功或收到回复|
|HTTP dispatched|transport前持久hook、wire哈希/SDK消息匹配|远端已理解Steer|
|Response observed|SDK返回headers、真实Chunk计数、可信终态分别记录|模型按要求执行|
|Semantic adherence|真实工具顺序/结果及最终语义独立评审|所有未来模型都遵从|

专门Mock让第二请求在HTTP门被拒绝：Steer仍可显示applied，reservation存在但HTTP0、provider response=false。此验收必须通过，不能把applied改写为成功发送。Fallback准入也可能在reservation前被拒绝，RuntimeAccounting的记录数是准入视图，不是实际HTTP账单。

首Chunk前可恢复错误仍遵守原Failover并逐次计数；一旦真正收到Chunk，不透明切换。每Case/总额独立，预算拒绝保存HALT并允许已有资源关闭。
