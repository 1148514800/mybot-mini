# Real Chrome synthetic acceptance

最终验收PASS，Playwright Python 1.64.1，Google Chrome 152.0.7977.83，headed真实页面。可选依赖仅通过`uv run --no-project --python 3.12 --with playwright python scripts/decision_browser_acceptance.py`在独立环境运行；生产pyproject.toml/uv.lock未变。测试专用服务入口scripts.decision_browser_server，显式注入SyntheticClient，监听127.0.0.1:8898。

先用本轮新建0700 profile A/B访问临时非生产同Origin，双向Cookie/LocalStorage标记不可见，核对不同user-data-dir。探针关闭后另建全新非符号链接UAT profile，核对Chrome启动参数和当前UID，sandbox开启、不复用用户Chrome。未操作8765、用户设置、旧聊天或默认profile。

真实点击新会话、发送输入、固定两约束、替换、撤销及确认弹窗；只读状态GET交叉核对来源与时间线，没有用后端写API冒充页面交互。错误模型回复仍在聊天正文，而可信面板只显示两条真实来源。兼容Pin不报假冲突；详情展示生效/失效顺序与来源事件。跨七轮后早期约束仍在实际合成请求。

完整SIGINT停止本轮服务并确认exit0、端口释放、Lease可再次获取；重新启动后真实页面恢复原Session标题、历史、Pin和时间线。启动阶段合成请求数未增加，旧approval/report/contract均为空；继续发送后仍含早期约束。替换/撤销历史在另一个会话也一致。

最终12次都是本地合成SDK调用，真实Provider HTTP/费用0。自身Chrome context关闭、profile移除、探针关闭、两次服务exit0，未删除锁文件。浏览器首轮驱动选择器误匹配嵌套summary，修正为面板直属summary后最终完整执行；无产品绕过或真实模型补跑。截图和最终动态隔离/清理证据见browser-evidence.json，PNG只含公开合成短句。
