# Operator Reliability Hardening与Steer/Stop Canary v3

未编号工程专题，不创建或改动历史Tag/ZIP。目标是可信操作员的端口/浏览器资源生命周期，不改变生产AgentLoop、Steer或模型权限。

流程：ports.bound_listener仅loopback、SO_REUSEADDR、不启用REUSEPORT，单次bind持有socket交给Uvicorn；service.OwnedService等待真正startup ready并核验自己的实际Listener PID/UID/PPID/argv/cwd/birth；browser_session在driver仍活跃时close一次Context，之后核实进程与profile身份再删除；sentence_diagnostics仅观察格式。新plan/budget/server/adapter/browser/prepare/mock建立N01/N02独立2次总额/1+1冻结门，正式Web/Agent/Failover/SDK接口和工具安全不变。

调用：browser.run→OwnedService→server.serve→原create_app/runtime；DOM动作→SteerInbox/Stop；adapter复用原真实SDK观察器与持久HTTP门；结束→原runtime清理→SDK/SQLite/Lease核验→自己的进程wait→Context关闭→Profile核验。port bind失败发生在app factory之前，不能生成Attempt或请求。

macOS/Python3.12+/uv：`uv sync --frozen`；`uv run python -m unittest scripts.check_uat_port_lifecycle scripts.check_uat_browser_cleanup scripts.check_uat_sentence_diagnostics scripts.check_streaming_steer_recovery_v3`；完整`uv run python -m scripts.check_phase`及报告列出的补充模块；`uv run python -m compileall -q mybot scripts`；`node --check mybot/web/static/app.js`。真实headed Chrome合成：`uv run --no-project --with playwright python -m scripts.streaming_steer_recovery_v3.browser --chrome <本机Chrome> --output <新私有目录>`，默认Mock；Live必须新精确GRANTED_2_REQUESTS。

案例：旧T01真实工具/Steer链路成功但全回复三句，旧结果FAIL保留；旧T02无Listener检查与bind差异导致启动失败的具体根因仍UNKNOWN。新独立实验区分socket绑定与应用ready，30轮原生Web同端口重启另有证据；不能倒填历史。原浏览器finally顺序问题通过资源生命周期修复，保留主错误和清理错误；句数不再漏掉相邻中文，但复杂文本仍要求审查。

实际最终测试数、Chrome异常路径及唯一prepare/freeze状态以[报告](../reports/streaming-operator-reliability-v3/acceptance-report.md)为准。旧报告、旧批次、用户Chrome/8765、main/Tag/ZIP不动。未授权不连接供应商。

最终离线2097去重unittest（新增78）与完整check_phase程序式检查通过；正常及业务异常Chrome自动清理通过，故障注入保留主/清理错误；N01/N02真实Chrome+SDK MockTransport通过、真实Provider0。唯一新批次prepare/freeze/verify完成，320源码hash一致，两库/工作区/配置身份完整、0 Attempt/reservation/HTTP，停在新授权门。实现SHA 07c25ce181b2af3dc368815ec4956a3ff05c75a2，预注册/冻结SHA 4a8fdb64a22811b20aebb85d1e1d25e9f385ad67。无编号归档，不生成或移动历史Tag/ZIP。

archive-ready: true
