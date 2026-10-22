# Full Coding Benchmark Batch 验收

**OFFLINE PASS / LIVE INFRA PASS**。自然组严格通过 **8/12**；所有结果与受控组分开统计。CLI退出码0不替代任务评分。

## 冻结与执行

独立分支codex/request-budget-full-batch，fetch基线3ccd2df6480f31dfc97ff26fcc181d24f1342971已核对。只读审阅第二次Canary：8次请求中最后响应执行额外校验，随后预算耗尽；Patch与Hidden Pass不能替代Agent合法结束，旧报告不改判。

Implementation：`fe3faa52f37ef6719d5e4cfc3c35421f3371d07c`。源码树SHA：`8fc9a11ac57039f413e559ee68c84e7de1564f2b5216e2ea9af0feabdc3342b0`。Live前已提交且干净；运行期间Python不改。macOS/arm64/Python3.12.14+uv，真实PTY与Seatbelt通过。配置coco/deepseek-v4.1-flash与coco2/glm-5.3-flash，Endpoint https://www.sub-coco.org/v1；复制现有Git忽略0600配置，未改Key。

Batch ID `1d627fe7983544c7847ffcf6424f3156`，开始（洛杉矶时间）2026-10-21T21:52:13.424332-07:00。一次启动以下命令，没有重跑或补测：

```bash
uv run python -m scripts.run_coding_failover_batch --live --confirm-api-cost --suite full12-plus-forced --max-physical-requests 204
```

自然组192、受控12（含1本地合成尝试），按Easy12/Medium16/Hard20、受控12分配。每例90/480/600秒、输出2048、SDK重试0。所有13个v4冻结包含源码/依赖/Benchmark/Judge/Schema/模型/配置及预算；批次计划先原子发布，每物理调用前预占持久账本。

## 修改与离线验证

只精简Controller.instruction与有效Revision/最后请求的收尾提示，不自动生成回复或verified，不重置预算；保留Patch、审批、沙箱、真实测试与跨模块约束。新Batch顺序复用原v4、AgentLoop、工具和Judge。原Loop、Patch、run_command、Seatbelt、Benchmark、Gold、Reference和隐藏评分未修改。

新增18项效率+25项Batch专项，接入全量；**1114/1114、31套件、零跳过**，保留原1071。原Failover50、生命周期42、CLI17和smoke13均通过，compileall/diff通过。没有放宽生产协议或旧断言。

synthetic前后对照在同5次预算下，旧脚本策略额外读取导致budget_exhausted，新提示使脚本verified；这只证明规则逻辑，不是真实模型改进证据。MockTransport验证受控主HTTP0、备用自己的Key/Model、sticky、3物理/2HTTP/3Controller，以及原生Patch/真实公开测试/Judge闭环。测试结果及日志SHA见offline-validation.json。

## 真实结果

自然12例完成12/12，Workflow Success 10/12，Hidden Pass 9/12，Strict 8/12。Hidden Pass但Strict Fail 1例。所有13个计划逐行结果与独立Attempt见case-results.md，未执行行保留UNSCORED，不删除分母。

| 难度 | 完成 | Strict / 4 | Workflow / 4 | Hidden / 4 | 平均物理请求 | 平均工具 | 平均可观察Token |
| --- | --- | --- | --- | --- | --- | --- | --- |
| easy | 4 | 3 | 4 | 3 | 9.25 | 11.25 | 38164.75 |
| medium | 4 | 3 | 3 | 3 | 8 | 12.5 | 34918.75 |
| hard | 4 | 2 | 3 | 3 | 11.5 | 17.25 | 59577.25 |

受控组结果：budget_exhausted / hidden_pass，Strict=False，回退=INJECTED。受控结果不并入自然故障率。

物理接口总计 **127/204**；真实SDK调用尝试126，可观察HTTP发送126，本地合成注入1。逐Provider物理：{'coco': 116, 'coco2': 11}，逐Provider真实HTTP：{'coco': 115, 'coco2': 11}。注入尝试占Controller、单Case与全局物理预算，但不调用主HTTP；随后真实备用使用自己的Key/Model并保持sticky，工具不重放。

可观察真实输入/输出/总Token：555553/19698/575251，真实Usage完整=True。合成注入Usage为null；不把缺失值推算成0。费用unknown/null，不是免费，204是次数上限不是美元金额上限。HTTP钩子是发送前观察，不是供应商计费确认；供应商内部路由不可独立核实。

Codex逐条安全审批20次，拒绝0次；完整有效argv和python -c代码逐次审核，当前公开候选/测试无凭证读取、网络外发或越权副作用；临时文件仅在沙盒scratch。逐次读取真实PTY新nonce，没有裸yes、管道、复用或预输入。审批只存类型、文件哈希、安全结论，不保存明文nonce/敏感命令正文。

## 证据、效率与局限

batch.status与每个已启动v4.inventory交叉检查身份、冻结SHA、raw/terminal/finished、请求reservation/outcome及唯一Attempt。所有已完成槽清理确认、无执行不确定、Journal归属异常、Index/受保护/无关修改、协议配对异常或越权审批；工程判定独立于TASK PASS。原始blocked记录保留，普通任务失败继续，安全异常则停止。

请求效率的直接观察是逐例物理/逻辑请求、工具顺序及有效测试后的额外工具，见batch-summary.json。新旧Canary预算和采样不同，不能由本轮与旧8次单Case比较断言因果提升；synthetic也不证明真实模型改善。失败分布、Patch阶段与无法确定部分见failure-analysis.md。自然回退是否发生，必须以各自然行fallback字段判断，NOT_TRIGGERED不能记为恢复PASS。

原始目录：`/Users/godblack/.codex/worktrees/request-budget-full-batch/mybot-mini/runs/coding_failover/full-batch-001`。evidence保存逐字节v4脱敏副本，request-accounting保存完整请求元数据和所有原始JSON SHA。没有完整Prompt、回复、原始Patch或凭证。历史Phase25、两个Canary、blocked、main、Tag/ZIP和用户文件哈希检查保持；不把新结果拼接旧Phase25分母，不移动Tag或Merge main。既有ExFAT ._pack警告未修复；Git必要操作可用。

下一阶段：见next-phase-readiness.md。当前只交付独立实验与工程结果，不宣称全任务通过、自然故障长期恢复率或总体模型成功率提升。Acceptance提交在Live后生成，仅Push独立分支并核对远程HEAD。

## 最终审计补充

Batch墙钟耗时1229.783秒（包括Codex逐次审核等待），所有13个自然/受控槽均各运行一次，无取消或Supervisor审计暂停。自然组SDK=HTTP=115；受控物理12=本地注入1+真实GLM SDK/HTTP11。全局127/204，不存在第14个Attempt。原raw的global_physical_request是v4单次执行内预算计数；新增batch_physical_request为全Batch连续1–127，不混用作用域。

受控组repeated_actions=1如实保留；这是模型重复动作计数，非客户端自动工具重放。正式Patch只有一次，所有工具调用ID及账本配对。自然12例回退均NOT_TRIGGERED，不能宣称真实自然故障恢复通过；受控INJECTED只验证本地明确故障后的备用真实编码链路，任务仍严格失败。

Easy/Medium/Hard的Strict分别为3/4（75%）、3/4（75%）、2/4（50%）。自然组10/12完成工作流、9/12隐藏通过；受控工作流0/1、隐藏1/1、Strict0/1。自然组1例Hidden Pass但Strict Fail，受控另1例。

281项历史/Canary/用户资产、main/Tag、配置哈希核对不变；全部13个工作区实际清理，没有仅凭标志推断删除。预期交付的8个文件齐全，原始证据校验清单见request-accounting，完整保护检查见batch-summary.audit。

请求效率仍无可泛化的真实改善结论：本轮有两条额外探索命令、Hard案例测试runner选择失败，以及受控Preview纠错；8次旧Canary与新12/16/20预算不可直接作因果对照。后续应离线研究测试入口反馈和请求使用策略、完善edited_unverified失败标签；不改变本次评分或追加Live。
