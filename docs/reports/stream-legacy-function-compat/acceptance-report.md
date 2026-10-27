# OFFLINE PASS / D02 LIVE BLOCKED

本轮真实模型请求0，DeepSeek/GLM/语义摘要/Judge均0，不继承旧D01授权。基线72e5ef74fb574dc9212fca188112ef058e4762e1，独立worktree/分支codex/stream-legacy-function-compat，旧R01/D01及其HALT/评分/私有资产不改。

确认SDK2.32.0的{}可被解析为truthy ChoiceDeltaFunctionCall，name/arguments默认None。D01冻结代码的可达触发分支可确认指向legacy真值判断，但原始字段没有保存，不能断言实际对象为空或完整还原Provider根因。Synthetic不是旧Chunk重放。

生产仅streaming.py按字段/类型/extra区分空对象、真实legacy调用、非法结构，并在8块ring新增安全结构信息；app.js识别两个新协议码。空对象继续校验终态，非空或未知负载仍拒绝，不转换工具。真正post-finish payload、重复finish、缺终态、不完整参数、输出边界与close失败保持原标准。

最终源码上全量check_phase1734项及补充317项合计2051个去重unittest PASS；本轮新增67（Legacy34、D02预算/冻结33）。9组历史独立补充129、旧UAT30、协议/关闭/SSE58、D01专项33均实际运行。运行411.46秒，结果ID无重复；全部Python/JS源码hash在权威测试前后及结束后复核一致，compileall、JS语法、diff检查通过。没有删除旧断言或以历史通过数冒充本次执行。

221块明确Synthetic空对象样本PASS；带Usage尾块222块并可信记录Mock7/9/16；同结构含真实函数名FAIL且0工具，每个SDK回归1次Mock HTTP。浏览器A–E及Steer/恢复A–H全部验收通过，5+10次Mock模型HTTP，7次自有服务正常wait exit0，端口/Lease/库一致，新profile清理。queued/applied/not_applied分别验证，原请求未被改写，无旧工具重放。

Implementation `3a906311a196f23e01227fd3ec9f0b212047b70b`，Preregistration/冻结源码 `06d53077c3f35985506c835b42d29fd8cd394aa7`。已按顺序唯一prepare、唯一freeze、verify；292源文件hash与权威回归完全一致，原Provider字节、workspace字节/inode、两库inode/完整性验证通过。D02独立端口8900可绑定、Lease可用、事件库空、0 Attempt/0 reservation/0 HTTP/0真实请求。单Attempt、全局1次预算、stream/include_usage保持，工具/MCP/Skills/Coding/Steer/摘要关闭，SDK retries0。Acceptance仅更新文档和脱敏证据，冻结后无源码修改。

原Provider真实行为仍UNKNOWN；本轮不宣称真实DeepSeek兼容已经PASS。旧R01/D01结果保持失败，不能补跑或挪用额度。

本次没有新的真实D02终态、EOF、延迟、Usage或费用证据；模型窗口/远程凭证有效性/真实兼容性均未验证，未来需新的精确GRANTED_1_REQUEST。冻结证据见d02-freeze-evidence.json；最终Acceptance提交及远程HEAD由Git交付核对。

交付附注：Push成功后只读核实外置盘._pack索引警告为AppleDouble旁文件，正式pack验证exit0；未清理共享Git对象库。远程HEAD已核对，源码/冻结不受影响，环境警告保留记录。
