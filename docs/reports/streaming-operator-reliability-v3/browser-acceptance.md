# Headed Chrome合成验收

全部模型请求由真实AsyncOpenAI SDK经过httpx.MockTransport，远端请求0。Playwright 1.64.1、Chrome 152.0.7977.83；新0700非符号链接Profile，实际启动参数/UID核验、sandbox启用；不复用默认Chrome Profile，不弱化安全策略。

| 场景 | 结果/证据 |
|---|---|
| A 快速重启 | 30轮原生Web、同端口、exit0，另N01→N02同一端口 |
| B 服务启动失败 | 真实外部Listener占用，port_in_use为主错误、exit1，未建Attempt/账本，Chrome/Profile自动清理PASS |
| C 浏览器操作失败 | Context后、导航、Steer、截图故障分别保留固定主错误；服务与Profile自动清理PASS |
| D N01 | 真实DOM queued后not_applied，UI“本次补充未生效”与“填入下一轮消息”可见 |
| E N02 | 真实DOM Stop后SDK关闭、cancelled，不可信部分/Usage null |
| F 刷新/SSE | N01/N02分别刷新并等待超出原2秒SSE重连周期，持久HTTP计数1/2，不追加请求 |
| G 多Case同端口 | 两个服务exit0、端口无Listener、SQLite/Lease释放 |
| H 异常清理 | 实际Context关闭后注入关闭错误和Profile删除错误均保留失败；后者单独核实清理测试目录，不冒充自动PASS |

双Profile同本地测试Origin Cookie/LocalStorage双向隔离PASS，探针服务关闭、测试目录移除。另实际无效Chrome路径测试确认启动失败时close调用0、无Chrome残留并清理自有目录。单元注入补充SSE/任务/停止超时等路径，不冒充这些是供应商真实故障。

截图仅activity区域（timeline/Pin/contract遮罩）和N01提示，不含模型正文/原始请求/Cookie。结构证据和故障记录见browser-evidence.json、browser-cleanup-evidence.json、browser-isolation-evidence.json。
