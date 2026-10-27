# AI_HANDOFF

## 当前状态

codex/stream-legacy-function-compat基于72e5ef74fb574dc9212fca188112ef058e4762e1。空legacy兼容修复与全部离线验收完成；真实模型授权0/请求0。D02新批次尚未创建，下一步先Implementation/Preregistration提交，再唯一prepare/freeze。

## 实现与验证

生产只改streaming.py与app.js。已知空dict/SDK模型按name/arguments/extra判断，不用对象真值；非空/未知legacy为unsupported、错误类型invalid，真正终态后输出独立AFTER_FINISH。8块ring含固定类型/饱和长度/计数/empty标志，无函数名/参数正文。不改工具、Failover、Pin/TaskContract/Decision/EventStore权限语义。

SDK2.32.0原始SSE证明{}解析成truthy模型，缺失/null与空对象字段集合不同。221块Synthetic空对象自然EOF、带尾块Usage可信，真实函数名Synthetic拒绝。D01可达legacy分支确认，原字段值无法恢复，旧FAIL不改判。

权威最终源码check_phase1734+补充317=2051个去重unittest PASS，新增67（Legacy34、D02门33）；source hash运行前后及结束后保持，compileall/JS/diff通过。headed独立Chrome双profile隔离与Legacy5场景、Steer/恢复8场景通过，共15次Mock模型HTTP、7次自身服务exit0/资源释放，真实0。报告docs/reports/stream-legacy-function-compat/。

## 下一步与禁止事项

完成Implementation与Preregistration提交，工作树干净后对~/.mybot-mini/uat/stream-legacy-canary-20261027/执行唯一prepare/freeze/verify；只能更新后续报告，不再改冻结源码。D02端口8900、唯一新消息、空Registry、1次物理/HTTP硬上限。必须未来新的精确GRANTED_1_REQUEST才能Live。旧D01/R01私有数据库未打开、旧报告/Tag/ZIP/main不变，不补跑、不复用额度、不操作用户Chrome/8765。
