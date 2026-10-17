# AI Handoff

## 当前目标与状态

Phase16检索与合成Agent Harness已实现：17项检索专项、24项Harness专项及编译通过，Phase15原39项通过；全量354项与Phase1/2原断言、归档安全检查通过，尚未创建phase-16 Tag/ZIP。不运行Live、不Push、不进入Phase17。Phase15已按用户要求推送（main 05c4310/phase-15）。保留用户mybot/app.py三处注释和workspace/instructions/USER.md未提交修改，不混入阶段提交。

## 实现与架构

- discovery.retrieval_mode可选literal/bm25/hybrid；缺省literal且旧默认对象不新增键。Literal原6/3/1不变；Catalog权限过滤、240字符描述、query/结果限制、激活原子性、请求快照不变。
- retrieval.py纯Python加权字段BM25：k1=1.2、b=.75、IDF log1p((N-df+.5)/(df+.5))、字段6/3/1；英文casefold/标点分词，中文单字/双字。别名字典独立、最长匹配、最多16次/32扩展词，hybrid=原始BM25+.35别名BM25，不是Embedding语义搜索。索引只取Catalog，不读真实文件/Schema/Gold。
- 独立tool_retrieval评测36例（32正/4负、8条保留表达），Hit/Recall/MRR/NDCG@1/3/5和语言/类别/分母；与Phase9评分和Agent成功率分开。
- tool_agent.py复用原AgentLoop/Manager/Context/Registry；MeasuredAgent只观测执行/收尾，无新循环。12内置合成任务、三模式，每次临时空Workspace/新Agent/Session，关闭持久化/Skills/DEBUG，强制只用本地35工具Demo，不连接用户MCP。Gold仅评分，Live用户Prompt不注入Gold。
- Live必须双开关；SDK retry=0，共享请求预算，固定输出/案例/重复/ReAct/Context/请求/任务/总时间限制；顺序seed仅洗牌，不是模型seed。asyncio.timeout围住MCP进入/调用/退出同owner Task，取消正确清理，不wait_for整个Agent。
- Usage真实字段优先，缺失/缓存未知为null，不字符估Token；显式价格且必要Usage完整才estimated_cost，不是账单/硬费用上限。报告不存Prompt/回复/参数/异常/URL/密钥；记录Commit/dirty/case哈希/配置摘要，--save独占写忽略runs/evals。
- Demo仅扩三个固定结果CODE-1/EVENT-1/DATA-1与42行，35工具Schema/原TASK-DOC行为不变。原AgentLoop、Registry、Planning、Session、Manager/Adapter/认证响应边界、Phase9评分、依赖锁文件均未改。

## 修改文件

新增retrieval.py/retrieval_aliases.py、evaluation/tool_retrieval.py/tool_agent.py、两个evals案例集、三个evaluate/compare入口和两个check脚本、phase-16学习文档；修改discovery排序/验证、两配置模板、Demo返回值、check_phase、README/索引/本交接。仅提交本阶段文件。

## 测试与实测

检索17项、Harness24项及Phase15原39项通过；编译mybot/scripts通过（先清理35个经文件头确认的AppleDouble）。覆盖公式/分词/词典边界/权限、指标多目标与负例分母、默认不建真实Client、Live开关/预算/retry/Usage/估价/隐私、真实stdio三组流程/配对/同批快照、错误参数/自报完成不算成功、恢复错误、超时与取消清理、Phase15比较不变。

36例Hit@5 literal .59375 / bm25 .625 / hybrid .875；负例空结果率均1。Agent固定脚本12例/模式：eager12成功25请求、literal11成功49请求、hybrid12成功51请求；累计Schema1461425/167123/175363。Literal中文agent-08检索失败明确保留。全部Token/费用/Live成功率未知；真实LLM与真实第三方MCP均未调用。详表/本地计时在phase-16学习文档。

## 限制与下一步

小内部合成集与受限词典不能泛化；ID/数值最终答案rubric不是自然语言语义验证。Live API/模型选择能力/费用未实测，Usage仅兼容标准字段；静默忽略tools的Provider不能自动证明不兼容。无Embedding/动态启动/list_changed/新权限。全量354项、原断言和归档安全检查通过，已审查待提交源码/合成数据/文档及跟踪文件边界，补archive-ready并commit；使用干净APFS worktree save16，核对旧15 Tag/ZIP后独立restore/冻结安装/全源码编译/全量及两组对比，补最终验证记录。不得覆盖用户改动、旧归档、Push或进入Phase17。
