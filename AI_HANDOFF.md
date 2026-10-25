# AI_HANDOFF

## 当前状态

Persistent Session Live UAT离线准备，LIVE_AUTHORIZATION=NOT_GRANTED；真实请求0/16，L01/L02/L03无Attempt、均BLOCKED。独立分支codex/persistent-session-live-uat，基线75cfcd6e1e04ab4d755aa2edf541a08dfedc9da7；不合main、不创建Phase/Tag/ZIP，不改生产mybot或原Harness。

## 已准备

- scripts/persistent_uat：冻结9+4+1条自然输入、实际Web Pin确认/替换/撤销/重启步骤、Unicode来源跨度、评分与停止规则。case预算10/4/2，全局16；NOT_GRANTED在凭证/SDK/账本变更前拒绝Live。
- 复用原UAT Ledger/SDK adapter的HTTP门与settlement，新增独立持久16预算；重启不重置、case单Attempt、SDK/重定向二次发送拒绝、备用同账本、意外摘要计保守reservation后停止。新22项MockTransport门测试通过。
- 原真实create_app/ChatRuntime/AgentLoop接入仅在新测试adapter，生产源码不变；新APFS可丢弃workspace与私有空SQLite，默认模板预先创建，MCP/Skills/Coding/命令关闭、文件只读、deterministic摘要、估算输入14000/输出1800。
- 准备目录 ~/.mybot-mini/uat/persistent-session-20261025；真实模型配置仅本地只读核对存在与模型名，远程凭证有效性unknown，不复制Key。真实账本0 reservation、0 case。

## 证据与下一步

预注册/报告在docs/reports/persistent-session-live-uat/。原1618基线文件保持，新22门测试及相关专项通过，计数/日志hash见offline-preflight.json；不把MockTransport的14次流程调用计作Live，不声称DeepSeek语义成功。离线L02已知无关产品单元损失0/0/3/5，是下界，真实助手信息损失未评。

已从干净预注册提交86105406ed46c32024a4c8d7d669eaaf6ca0be10完成私有freeze.json冻结与verify；后续报告提交为Acceptance，仅核对专题Push与远程HEAD，之后停止；没有新的人类GRANTED_16_REQUESTS不得启动Live。未来先核对freeze.json、配置、DB inode、工作区指纹、账本、进程退出与lease，再按冻结顺序一次运行。不要重跑旧Live、复用余额、改消息追求PASS、自动新建批次或修改生产源码。
