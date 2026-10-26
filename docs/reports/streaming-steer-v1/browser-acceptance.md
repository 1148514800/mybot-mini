# Headed Chrome synthetic acceptance

最终动态验收PASS。Python Playwright1.64.1，Chrome152.0.7977.83，独立0700 profile、sandbox开启，核对真实--user-data-dir与UID。先使用新A/B profile做同Origin Cookie/LocalStorage双向隔离探针，再另建UAT身份。不复用用户Chrome、不访问8765或私有Live库。

复现：`uv run --no-project --python 3.12 --with playwright python scripts/streaming_browser_acceptance.py`。仅可选临时环境安装Playwright；生产依赖与uv.lock不变。服务scripts.streaming_browser_server在127.0.0.1:8899，实际OpenAI SDK2.32.0解析本地MockTransport延时SSE，所有headers/传输均不访问真实Provider。

|场景|实际页面验收|
|---|---|
|A|终态前出现中文/Markdown安全预览，running时SQLite尚无assistant.message；正式保存一次，无script执行。|
|B|在完整工具调用前真实提交Steer；原SDK请求不变，工具未启动，下一请求有来源Steer及配对的未执行结果，applied。|
|C|最终文本无下一步骤，not_applied且仅一次请求；点击填入下一轮仅填文本，不发送。|
|D|输出一半加部分工具参数后断流；provider_error与不完整提示，没有执行工具。|
|E|浏览器网络真实离线再在线，Agent继续，重连同一行不重复，模型请求不增加。|
|F|真实命令审批面板等待时Steer禁用；测试明确点击拒绝，命令未执行，没有自动授权。|
|G|停止并重启自己的合成服务，历史Steer只作审计，预览/审批/Receipt/verified不恢复；启动零模型请求和工具重放。|
|H|真实停止消费中的流，记录cancelled、丢弃pending Steer，不保存成功最终回答。|

最终浏览器轮8次SDK Mock HTTP、8个流关闭观察；Steer一次applied、一次not_applied、一次discarded_on_stop。数据库integrity/FK通过，7用户消息/6助手消息（取消轮不伪造最终答复），Pin0；唯一tool是被拒绝命令，effect=none。两个自己服务exit0，端口/Lease释放，profile清理，保护Fixture字节未改。详情与脱敏截图SHA见browser-evidence.json；不提交原SQLite、profile或完整SDK请求。
