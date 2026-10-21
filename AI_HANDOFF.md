# AI_HANDOFF

## 当前状态

Provider Failover Harness Integration：Phase25之后的独立可靠性改进，不是Phase26。
独立codex/provider-failover-harness分支，远程验收基线5490149827cffbc5c75aa6cc1634efeb33344c0a已核对无更新。
新增49项专项、全量1070项/29套件及Phase1/2兼容断言通过；原1021项不删、不跳过、不弱化。
本轮真实模型API请求0，不使用此前剩余额度，不Push/Merge、不移Tag或生成ZIP。

## 实现与隔离

- 新coding_failover适配原run_task，复用ProviderFailoverClient可选recoverable谓词；CLI缺省策略不变。
- 新evaluate_coding_failover默认single/offline，只有显式failover启用严格策略；旧入口和单模型字段兼容。
- 严格回退仅网络、超时、429、500/502/503/504；参数、认证、协议、本地异常、取消不回退。
- 原Loop预占主请求Controller预算；备用前先检查Attempt、时限及全局预算，再预占Controller。
  TracedClient使用逻辑影子计数，全局物理计数只在SDK接口调用前增加；每Case Controller还受全局剩余额度约束。
- 同Attempt Sticky、下Attempt从coco开始；逐Attempt延迟创建备用并有界关闭两端。
- SDK尝试、HTTP发送尝试及离线合成接口明确区分；无HTTP观察或Usage时为null，不假定为0。混合费用未知。
- 新create-once v4 manifest只写runs/coding_failover，每目录一个Case/Attempt，不提供重放/续跑。
  冻结实际配置/源码树/模型/策略/预算/依赖/Benchmark/评分，交叉校验身份、SHA和请求模型。
  失败、中断、不确定清理与缺失证据保留blocked。离线执行不计Live严格成功。

## 验证与证据

49项新专项、原17项CLI回退、13项smoke、42项生命周期专项以及全量1070/29通过，编译/diff通过。
合成故障后原Loop完成真实Patch、Seatbelt公开测试和Judge：5次逻辑请求=6次物理接口尝试，Revision1/1，ID配对与Journal正确。
回退后读取不重放；取消、迟到响应、全局/Controller预算、认证协议、异常关闭、历史隔离与防篡改均有反例。
实际SDK MockTransport验证自己的模型/Key、相同上下文/Schema、禁隐式重试和HTTP计数，无外部模型网络。
无需要Codex代答的CLI审批提示，operator yes输入0；真实PTY/nonce由既有42项合成生命周期测试覆盖。
验收入口docs/reports/provider-failover-harness/acceptance-report.md；架构/命令docs/provider-failover-harness.md。
原始测试日志/tmp/failover-harness-*.log，不提交原始日志或配置。

## 下一步与边界

本轮未复制真实配置到开发区，未改任何已有Key。1592项保护资产需提交后复核保持。
原Phase25/DeepSeek Campaign及CSV blocked证据不变，不允许在新分支继续或拼接旧单模型结果。
可在本次OFFLINE PASS之后另行授权独立Live Coding Benchmark，必须配置凭证、冻结新版本并单独统计混合模型。
不能宣称Live PASS、编码成功率提高、真实故障恢复稳定性或取消长期可靠性通过。
AppleDouble pack索引错误未清理，Git必要读取与完整保护核验可用。
