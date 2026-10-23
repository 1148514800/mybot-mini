# Targeted UAT v2：OFFLINE READY

**LIVE_AUTHORIZATION: NOT_GRANTED。未执行Live，真实模型请求0/34。** 本轮完成全新任务、离线测试、实际环境预检、浏览器审批演练及冻结，不给T01—T03任何Live PASS/FAIL判定。

基线 92424d080e31cefa2adf3af4c507d8f17a0669c0，分支codex/targeted-user-uat-v2。Preregistration Commit：67b3ed09cb57f2b35e3c530fde70c35a6abb8bd6；本报告所在后续docs提交是Acceptance Commit（以Git查询该文件最近提交为准）。本机独立冻结包保留，SHA、代码/配置/Fixture/账本验证见 [freeze-summary.json](freeze-summary.json)。正式SQLite仍0个Attempt、0个reservation。

| 任务 | 离线准备/验证 | Live状态 |
| --- | --- | --- |
| T01 标签整理 | 新APFS Fixture原生Preview PASS；公开/独立初始Bug确认；真实工具合成闭环PASS | NOT_RUN_NOT_AUTHORIZED |
| T02 订单汇总 | 两文件Preview PASS；只修helper的负例仍失败；真实工具合成集成/Revision测试PASS | NOT_RUN_NOT_AUTHORIZED |
| T03 五轮照片讨论 | 固定12000输入预算，合成前4轮无摘要、第5轮semantic_applied；5主+1摘要、Session/文件不变 | NOT_RUN_NOT_AUTHORIZED |

原38套件1354项、旧UAT13项、修复专项42项共 **1409项不回归**；新v2专项 **24项通过**，合计 **1433项通过，0跳过**。包括原生工具合成Coding、持久34次/逐Case预算、MockTransport Primary/Backup/摘要/失败/重试拦截、完整Web驱动MockTransport组装、授权门、冻结篡改与一次Attempt协议。指定重复专项不重复累计；compileall/diff检查通过。见 [offline-validation.json](offline-validation.json)。

## 11项问题的证据边界

1. 原生Patch Preview在新的合规T01/T02目录实际通过只读预检；**真实模型驱动Preview未验证**。
2. 真实模型能否使用Receipt正式提交：**NOT_VERIFIED**。合成Client只从可见响应取Receipt，原生提交与文件变化已离线验证，不能算真实模型成功。
3. 单文件Coding的Agent自身unittest：真实模型未知；真实浏览器合成演练运行原生命令，3项测试通过、revision1 verified。
4. 跨文件业务入口：公开与独立oracle在原始源码失败；只修helper仍失败；合成闭环真实修改两个模块、独立断言及Agent测试通过。Live未知。
5. Controller当前Revision：T01/T02合成闭环均verified；真实模型verified数0，未执行不是失败。
6. Web审批：**真实浏览器离线逐次批准1次**，Live审批0、终端人工yes0。核对固定Python、cwd为独立Fixture、unittest discover、30秒、macos_readonly、工作区只读及无网络，无缓存授权或nonce复用。
7. 实际语义摘要：真实API请求/应用均0；合成校准1次请求、1次应用，不冒充Live。
8. 摘要准确性：合成引用/早期约束送达与完整Session可验证；真实模型是否准确保留早期/最新约束、决定/未知/未实现仍未知。
9. 无效语义请求：本轮没有任何Live摘要请求，不能据此声称真实无效调用率为0；只报告合成成功和固定触发。
10. 是否适合受监督日常使用：**真实核心能力仍NOT_VERIFIED**，离线READY只是允许在独立授权后开展监督验收的工程条件，不是日常可靠性结论。
11. 当前阻塞/未知：**授权未授予，Live停止在执行边界**；未确认需修生产的阻塞缺陷。最重要三项实测未知仍是真实Coding闭环、摘要保真、实际请求/Token费用。

DeepSeek0、GLM0、真实语义0、HTTP供应商发送0；Fallback NOT_TRIGGERED；供应商Usage=null、cost=null（未执行，不伪造0 Token或美元上限）。未用旧22次余额、无付费Judge。正式Fixture无文件/Index污染，无Live不确定执行。开发中一次合成解析异常安全停止及修复如实记录于 [失败分析](failure-analysis.md)，不改变旧UAT结论。

生产mybot/、旧scripts/uat/、旧测试/Judge、历史报告/main/Tag/ZIP均未改。所有基线文件除交接快照外逐字节核对。截图仅是明确标注OFFLINE/SYNTHETIC的真实浏览器演练：[回复](offline-browser-reply.jpg)、[验证面板](offline-browser-verified.jpg)。SHA清单见 [evidence-sha256.json](evidence-sha256.json)。

未来只有用户明确授予GRANTED_34_REQUESTS，才可对本冻结包重新验证前置门后执行各Case唯一Attempt；不得改任务/预算/配置/源码追求PASS。当前不推定授权、不启动新Live。完整自然消息、公开合同、隐藏断言归属及四轴评分见 [预注册](preregistration.md)。
