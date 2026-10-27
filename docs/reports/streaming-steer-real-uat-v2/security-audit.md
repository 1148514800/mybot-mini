# Security audit

本轮NOT_GRANTED，真实Provider0；所有SDK演练由MockTransport拦截，不读真实配置来发请求，prepare仅本地指纹/模型/凭证存在检查。旧GRANTED_1_REQUEST不被新入口接受，--live授权在读取批次/Provider之前检查精确GRANTED_6_REQUESTS。

只新增UAT与文档，mybot生产源码/静态资源/pyproject/uv.lock、旧UAT脚本与所有旧报告保持。原Tool Authority、Controller、Web认证/CSRF/CSP、Pin/TaskContract/Decision/EventStore业务语义不改。Registry局部限制不包装原工具、不增加权限；未知工具实际尝试记安全异常，HALT后续。

每次SDK之前持久预留，HTTP前记数，重启不重置；6总额和4/1/1 Case上限、唯一Attempt、顺序、无余量转移、无摘要/Judge。HALT保持第一原因，仍允许原生关闭自己的资源。关流失败不能结算或放行下一Case。

首轮新观察器因元数据字段重名而采集失败，修正为不同时间/布尔字段，原失败日志hash保留；未改生产、删除断言或重做冻结。配对观察增加批次索引，防止重复tool结果复用旧匹配。所有这些均在唯一prepare/freeze之前完成。

不提交完整请求/回复/原始Chunk/工具参数/密钥/Cookie/CSRF/nonce/SQLite/Profile。只发布静态许可工具枚举、Fixture分类、ID/hash、布尔和固定结构。旧R01/D01/D02私有库未打开，原用户Chrome、8765、私人工作区未访问；不清理共享Git AppleDouble旁文件，只读检查并记录。
