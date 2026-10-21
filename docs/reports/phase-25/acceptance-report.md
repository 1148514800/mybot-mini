# Phase25 最终验收

## 分项结论

- Harness新增编排及统计、32+1新增离线测试通过；原916项保留，全量949项/25套件通过。审批值守中断暴露的停止边界已修复，修复后未重跑标准付费Cohort，因此长期运行可靠性只作条件验收。
- 标准12×3槽实际完成36/36；完整成功15/36，Round1 9/12（75%）、Round2 6/12（50%）、Round3 0/12。所有失败保留分母，未执行0，不确定的未落盘槽0；其中13次操作中断必须调查，不能当作有效模型能力失败。
- 三轮稳定性未验收：后两轮受审批值守中断混杂；不能从这些比例推出模型稳定性。每例至少一次覆盖11/12，timezone未有本Cohort完整工作流成功，不叫pass@1。
- 外部项目：未完成/失败（见独立证据），其版本独立于标准Cohort；只支持一个小型公开Python任务的有限泛化结论。
- 归档对象是本次工程、真实失败和证据快照，不将能力或稳定性标为全部通过。归档实际创建、SHA及还原结果见Tag目标与归档旁验收回执，不覆盖Phase24。

## 版本与执行

benchmark_harness_commit：`b008f35563c266d89ebbdd67a3c31607f9c47819`。所有标准报告均同一coco2/gpt-6-astra、macOS arm64、Python3.12.14、原Benchmark/Grading/uv.lock哈希和固定预算。每案例12模型请求，输出2048，单请求90秒，任务600秒，总900秒；命令30秒不变。配置SHA：`4744178d9d033a202e1b09518c167218309f7b8ceb5031de3357a2967562ca54`。

事后停止边界修复提交`29fedef44f60c2bdda405dce8390f2606aba9319`；外部任务Harness：`e7a1f396ffe95acfb52e10277b09287649c3e193`。final_report_commit为annotated `phase-25^{commit}`解析所得目标，不能代替标准执行提交；自身SHA不写入自身以免循环。

入口：evaluate_coding_campaign init/run/status/export复用原evaluate/AgentLoop/Controller/ToolRegistry。started/raw/finished独占、fsync、SHA验证；完成跳过，未知/中断停止，不自动重放；离线默认无API。V2继承真实终端的独立进程运行单槽，原生审批不变。

## 标准结果与资源

完整36行、12×3矩阵、难度、分位数、工具成功统计及每请求计划分组见benchmark-report.md/benchmark-summary.json。Easy 7/12、Medium 4/12、Hard 4/12完整成功；Judge hidden_pass31/36、Judge verified_repair18/36、Agent verified15/36。

请求308、成功响应307、已完成工具调用540；Patch预览41、提交31/34尝试；真实Agent测试18。已知输入Token1,021,493、输出99,643，总Token1,121,136（仅35/36报告的已知小计；完整总量null）。逐报告耗时合计10,947.906468秒、P50 177.861、P90 600.549、P95 600.554；记录区间墙钟14551.566秒另含槽位间解释器等待。价格表缺失，所有估算费用和单位成功费用null，不代表免费。输入输出Token和请求延迟分布见JSON。

## 失败归因与下一步

1. 13次审批值守中断后等待600秒取消：旧编排未把cancelled/task_timeout作为停止边界，继续运行后续槽位；取消后原capsule清理导致13次Journal归属不匹配、累计26文件。未批准过期提示。事后添加runtime错误/取消/未完成命令调查门和进程退出上限，离线证明流程改变，不伪称标准Live验证。
2. 3次请求预算耗尽但已有通过当前修订的真实测试（timezone两次、cli一次），Judge通过而Agent未verified；Planning/结束请求开销有改进空间。成功的PLANNED运行也存在，不能直接禁用Planning。
3. pagination R1与cache-ttl R3正式Patch参数错误；预览成功不证明正式提交参数一致，脱敏报告不足以指认具体字段。validation-chain R3第5次响应预览成功，第6次正式提交遇到stale_file_hash且safe_to_retry=true；第7次响应重新读取3次后触发max_no_progress。无实际提交，不能称为反复预览失败。保持原安全恢复边界。
4. file-recovery R1一次API请求超时；其前已有4次响应，不能说整个案例未收到任何响应，也不能无证据区分网络/Provider后端。
5. serialization R3请求预算耗尽且没有提交/测试；隐藏失败针对未修改基线，不能推断未提交候选的正确性。

Phase26建议：可取消、可观测的逐命令审批生命周期；取消后保留最小归属/审计证据；为最终测试与verified收尾保留预算的通用策略；结构化Patch参数构造及脱敏失败阶段；在新授权、固定版本和持续审批值守下重新做干净重复Cohort。不得从本次单一模型/一次外部任务直接转向多Agent或RSI。

## 安全与保留

标准Codex逐条授权yes18次，0拒绝；13次未回答不是拒绝、更不是批准。完成的18次命令均有原生Seatbelt/真实测试证据；os_sandbox请求字段本身不作执行证据。受保护/无关文件变更0、Index变化0、虚假verified0、工具ID全部配对、sandbox_failures0；Journal异常如上明确保留。外部宿主验证另批准6次，外部Agent命令批准0；总yes24次。第6次外部模型请求超时（6请求/5响应、13工具、0Patch、0Agent测试），泛化未通过，不扩大超时或重跑。

主工作区两处用户修改、原Index、75个历史资产/config/报告/ZIP哈希及原分支/Tag/远程引用检查保持（两条Codex内部turn-diff临时引用在后续复核时已不存在，不能宣称全部内部引用未变）；无Push/Merge、无旧Tag移动。原Phase24归档源3f53b05不同于ff10fb6基线，原两ZIP SHA仍3c69bb4eb29d982f3f8a9b1c1ea9fe968e098f1e58d3d5a04b8ca7a3fc5f8e09。

所有原始证据字节保留，finished/raw SHA及evidence-sha256.json核对；聚合报告脱敏扫描不输出凭证、原始模型请求或原始工具内容。SHA保护损坏检测，不对恶意同时篡改全部证据的宿主作不可伪造承诺。工具Schema补录明确标时，未冒充运行前清单。

## 未验收范围

原Phase24历史9/12（跨模型/版本）不能与本次Round1直接比较改动因果；本次覆盖也不等于生产项目泛化。36标准槽已耗尽授权计划，不自动补跑。停止边界修复只有离线和独立外部任务验证，干净的三轮稳定性需要新授权重新建Cohort。费用缺失无法补造。归档不附带真实API配置，独立还原离线测试不能证明真实Provider可用。
