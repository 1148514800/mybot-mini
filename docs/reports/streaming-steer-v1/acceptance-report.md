# Streaming & Steer v1 — OFFLINE PASS

基线c2f1baca04dc8b7bc320e9cd9295fe3d5b870331，独立分支codex/streaming-steer-v1。Implementation commit：f6eb05a75bd710438d026b1b761de3df6ba43a86。本报告单独Acceptance commit交付，最终远程HEAD在交付回复核对。

新增97项专项：Streaming33、Failover12、Inbox22、Web30。最终check_phase59组1734项，独立补充79、Persistent预算22、Source-Aware预算28，去重1863项全部PASS，0跳过；1766旧基线+97=1863。定向重复与浏览器检查不重复计入。最终Python/JS源码前后哈希一致，compileall、app.js/markdown.js语法与diff检查通过；旧断言保留。首次/中间版本完整检查通过后继续补严终审问题，最终结果单独记录，未用较早版本替代。

独立headed Chrome152.0.7977.83/Playwright1.64.1完成A–G加H停止，含双profile Cookie/LocalStorage动态隔离。最终8次SDK MockTransport HTTP和8次流关闭，原请求不变、未开始工具被Steer跳过、无下一步骤不额外请求、断流不执行部分工具、真实网络重连不重发/重复、审批未绕过、重启不恢复流/Steer执行。保护Fixture字节不变，SQLite/FK完整，Pin0，唯一工具为被拒绝命令且effect=none。

**真实DeepSeek0、GLM0、语义摘要0、付费Judge0、真实Provider HTTP0；未使用任何旧余额。**实际供应商Token0，cost=null（未建立部署价格）。Mock Usage不当账单：最终浏览器已知合成subtotal180，两个中断请求Usage未知，完整合成总量也不能记为180。

## 十八项合同回答

1. 真Streaming：启用时SDK stream=true，逐Chunk消费，终态前有真实页面预览；无先完整回复再切片，无第二次完整请求。
2. Tool Call：按index组装ID/名称/JSON，严格对象解析、索引/ID/终态/大小核验后规范化。
3. 部分参数：不得进入工具执行路径；缺失终态、无效JSON、断流与取消均不执行，原Registry/权限/审批继续生效。
4. Fallback：首个Chunk之前可按原恢复策略和预算切换；收到任何Chunk后禁止透明Fallback，包括role、Usage和工具片段及半程超时。
5. 计数：创建和消费共用一条物理记录，HTTP独立钩子，无隐藏SDK retry。运行中的物理与HTTP快照也已验证；多次观察不重复计数。
6. Usage：末尾choices空可携Usage；缺失、null、不可信或断流保持unknown/null，subtotal不等于完整供应商总量。
7. 刷新：从可信状态恢复显示，不发送模型请求，不自动取消后台Agent。
8. SSE重复：有界绝对文本快照+sequence/Turn/Stream/revision过滤；过期或未来cursor发reset，以状态恢复，不补造Token。
9. Steer生效：queued只是接受；下一安全步骤重建并通过Token/Controller预算，物理请求准入才applied，不承诺模型遵从。
10. 在途请求：不会修改；SDK请求证据核对字节结构相同。
11. 不要修改：到达未启动工具批前可阻止本批，生成配对的success=false/executed=false结果，再进入已有下一步骤。
12. 已开始工具：保留真实结果，不伪造未执行、不回滚未知副作用，后续调用再检查pending。
13. 失效Steer：停机/重启不恢复执行队列，只读审计；无下一步骤not_applied，可显式填入新消息但不自动发送。
14. 执行授权：不恢复旧审批、Receipt或Controller verified，不借Steer扩大命令/MCP/文件权限。
15. Pin/来源：模块与原消息未改。Steer独立schema v2来源事件，不自动生成Pin/confirmed_decision，不伪装初始TaskContract要求；v1暂不支持其改变可信合同。
16. 秘密：跨Chunk完整行缓冲后整体脱敏，长行/多行已知凭证保守隐藏，不发送工具参数或SDK错误。不是通用语义秘密识别器。
17. 额外模型：队列/显示/重连/恢复均不自动产生请求；最终文本无下一步时不续写。B下一请求使用原ReAct步骤和预算；未新增Judge或自动摘要。
18. 真实Provider：部署Streaming支持、非标准Chunk、Usage、速率/延迟、真实断线和Steer语义遵从仍UNKNOWN，需另行预注册授权。

## 交付与边界

新增agent/streaming.py、agent/steer.py；对原Loop、ProviderFailover、Accounting、EventStore/Schema及Web做小范围集成，默认关闭并保留非流式兼容。没有改成熟Memory、Pin、TaskContract、Controller或权限架构。真实浏览器与SDK证据/截图SHA见browser-evidence.json和evidence-hashes.json；完整分层报告在本目录。

Stream文本缓存32768字符、工具片段65536字符/16调用、行缓冲4096字符、预览8192 UTF-8字节、活动deque128、Steer单槽/每Turn最多32记录。关闭无法确认仍保持安全阻止和Lease，不以完成输出替代业务正确性。

未操作旧8765、用户Chrome、旧Live库、冻结账本、历史评分或Tag/ZIP；自身临时服务正常退出、端口/Lease释放、profile清理，无已知污染或不确定执行。旧代码写者升级仍须协调，不能共享不兼容活动事件库。详见security-audit与remaining-risks。
