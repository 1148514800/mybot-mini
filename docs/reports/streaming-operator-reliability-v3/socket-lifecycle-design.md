# 单一绑定与归属

`scripts/uat_operator/ports.py`为操作员工具，不是模型工具。Live入口先验证精确授权、冻结与未结算状态，再创建AF_INET/SOCK_STREAM，仅127.0.0.1、SO_REUSEADDR开启、SO_REUSEPORT关闭，执行一次bind/listen。socket始终持有并直接传给安装版本Uvicorn 0.54.0的Server.run(sockets=[sock])；不先释放、不随机换端口、不双重绑定。

只有bind成功才调用app factory；Case Attempt仍在原生lifespan启动。端口冲突时只有操作员状态文件记录固定port_in_use，未构建app/账本，不生成伪造Case结果、reservation或模型HTTP。现有HALT不解除。状态文件有bound/ready/closed/failed区分；ready只在Uvicorn完成startup后发出。

`scripts/uat_operator/service.py`从自己启动的uv子进程获取PID/UID/PPID/启动时间/精确argv/cwd/127.0.0.1 Listener归属；ready文件不能单独成为操作权限。Chrome随后核验原应用bootstrap。connect_ex不再作为启动依据；应用未ready不能发消息。外部Listener冲突必拒绝，即使是自己尚未关闭的旧Listener也不能共享。

关闭只向自己的launcher发SIGINT，必要时再次验证捕获的实际服务子进程完整身份后发SIGINT；未确认子进程绝不信号。超时/身份变化/SDK或Lease清理异常保留失败。退出0、无Listener、native SDK/数据库/Lease证据分别核对。socket finally关闭，不删除锁或修改系统设置。Uvicorn生命周期shutdown_completed及lifespan错误独立检查；不以端口释放代替exit0。

无释放再绑定TOCTOU；仍无法阻止操作系统/外部用户之后改变进程状态或文件权限，发生身份/ready/权限不确定时fail-closed。ready检查和真实浏览器操作之间仍可能应用崩溃，这属于运行失败而不是端口抢占被忽略。
