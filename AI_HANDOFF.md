# AI Handoff

## 当前目标与状态

Phase15工具发现/渐进披露已完成，39项专项、编译、全量313项及归档安全检查通过，独立ZIP安装/回归与还原验证通过；不进入Phase16。Phase14已按此前用户要求Push，Phase15默认仅本地。不改真实config/Session，不调用真实LLM/第三方服务，保留用户mybot/app.py三处注释和workspace/instructions/USER.md未提交修改。旧Phase1–14 Tag/ZIP不变。

## 实现与架构

- GatewayConfig新增严格mcp_discovery（默认off）；数量1–64、完整MCP Schema字符256–200000、搜索结果1–20。主模板默认关闭，config/mcp.discovery.example.json是35只读工具的MCP片段，需用户自行合入配置。
- discovery.py：Catalog只索引已注册、allowlist且非deny的原Adapter；本地冻结目录/引用，无额外tools/list、tools/call、审批或模型请求。query1–256可打印字符，描述240字符，Unicode字面关键词按名称6/Server3/描述1计分，同分全名排序；返回有界元数据，无Schema或认证配置。
- activate原子替换并去重；未知/原生/deny/数量/完整Schema超限保留旧集合。Schema长度按ensure_ascii=False的MCP定义数组计算，空0。激活不是审批，不执行业务。
- 同一Registry新增可选visible_names投影，默认原注册顺序/全部定义不变，无删除重注册。Agent每次请求重算Schema并冻结名称frozenset，同批先激活后调用不可绕过，旧已暴露者即使同批被替换仍按原快照允许；下一请求才见新Schema。任务起始/finally、clear、异常/取消/上限均重置。
- Tool提供显式provides_execution_evidence角色；Planning/Skill/Discovery标False，纯元操作绕过Plan门禁且不observe；真实业务沿原证据/审批。ContextManager不改，统计当次messages+tools、保留裁剪/预算失败/canonical Session。旧Evaluation显式禁MCP/Discovery隔离，评分器未改。
- 35工具真实SDK stdio Demo覆盖项目/文档/代码/日程/数据，仅合成只读内存结果。compare_tool_discovery.py用固定LLM脚本+真实SDK验证三任务六组，默认仅stdout统计，不保存提示词/运行日志。
- Manager/Adapter/Approval/传输/Bearer/OAuth/响应限制均未改，SDK/锁文件不变；没有第二个Registry、Agent循环、热更新或向量检索。

## 修改文件

新增mcp_client/discovery.py、scripts/{mcp_catalog_demo_server,compare_tool_discovery,check_tool_discovery}.py、config/mcp.discovery.example.json、docs/phases/phase-15.md；修改GatewayConfig、Tool base/registry/skill、Agent loop/planning角色、Evaluation runner隔离、check_phase、主配置模板、README、阶段索引和本交接。app.py/USER.md修改不纳入提交。

## 验证与测量

39项专项通过（34项目录/Agent/Context/Evaluation/比较、5项HTTP/Bearer/OAuth/审批）；原Planning12项另行通过，mybot/scripts编译通过。包含35工具真实发现、目录过滤/排序/边界、激活原子性、精确字符边界、同批快照/下一轮真实调用、生命周期、Plan证据、Skills/DIRECT、Context计量/失败/请求裁剪与原文、审批真实状态及配对、三种HTTP认证兼容、旧Evaluation隔离和debug隐藏query。Phase1–15全量313项unittest及Phase1/2原断言通过；归档安全集成检查通过。干净APFS worktree保存的ZIP和独立学习目录均完成uv sync --frozen、编译及全量313项/Phase1–2原断言；还原目录另编译scripts并重跑六组对比，统计完全一致。ExFAT还原目录编译前清理124个经文件头确认的AppleDouble文件。

离线对比（Catalog35工具；eager初轮40/58457字符，progressive初轮7/2520字符）：项目任务eager2请求/累积116914，progressive4请求/13280；文档查询2/116914 vs4/13320；两类别3/175371 vs7/25680。全部合成任务成功，真实业务调用1/1/2一致；额外请求+2/+2/+4。平均Schema字符等细表见phase-15学习文档。实际Token/费用/缓存/真实模型能力未知，没有调用真实LLM。

## 限制

词法搜索无中英文同义词/语义能力；描述是不可信元数据，长度/控制字符处理不是通用秘密脱敏或提示注入沙箱。仍启动所有配置Server并完整发现，本地Schema内存不减少；无list_changed/懒启动/重连。只限制模型可见性，可信本地Registry/Manager调用仍沿原权限执行，不是新沙箱。Session可保存查询/激活调用记录，但不恢复active状态。静态Adapter定义/单Agent串行任务，运行中修改Schema不受支持。探索消耗原ReAct预算；专用Schema预算通过仍可能超过总Context预算。离线字符节省不等于真实费用/能力提升。

## 下一步与不要重复

Phase15完成，等待用户下一项任务。不得改旧归档、混入用户修改、自动Push或进入Phase16。学习历史仅在docs/phases和Git。

实现提交79b1d55d8c1ca31cc059402d8d971df6750201ab；唯一annotated phase-15指向该提交。../mybot-mini-snapshots/phase-15.zip共123条目，SHA256：995431ec477bfd42b1a9fc3e0e2b7405d688d087f7931578296a254c00f3ef62。CRC/提交SHA/必要文件/无AppleDouble检查通过；旧14个Tag对象及ZIP哈希完全不变。restore_phase.sh 15还原到../mybot-mini-learning/phase-15，临时APFS worktree已移除。主工作区仅保留用户app.py与USER.md未提交修改。最终验证记录另作文档提交，不移动阶段Tag。
