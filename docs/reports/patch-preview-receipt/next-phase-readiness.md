# 下一轮独立 Live A/B 准备方案

当前仅离线可用，未获得新 Live 授权，不启动执行、不消费旧额度。建议 8 个新任务配对、16 个唯一 Attempt；任务需另行编写并冻结，覆盖 4 个常规边界修复、2 个多文件流程、2 个复杂文本变更。不得复用旧四对或本轮公开合成 fixture 作为 heldout。独立私有断言不送入模型，冻结 Judge、保护文件、样本和预期结果，保留所有失败分母，不按已知私有答案调参。

比较同一 Implementation 版本上的 Legacy（flag=false）与 Receipt（flag=true）；其余配置相同。主模型 coco/deepseek-v4.1-flash、fallback coco2/glm-5.3-flash；保留现有 network-timeout-429-500-502-503-504-v1、SDK retries=0、无工具重放。固定任务编号 1…8；每对执行顺序 L/R、R/L、R/L、L/R、L/R、R/L、R/L、L/R。各槽预先赋唯一 Attempt ID，冻结清单后不替换或补跑失败槽。

每 Attempt：逻辑模型请求最多 16、物理最多 16（包含 fallback）、工具 48、Write 3、命令 6、无进展 3、输出 2048 token、请求 90 秒、任务 480 秒、外层 600 秒。全局物理上限 256、全局时限 7200 秒；模型/工具/时间预算两组一致。硬费用上限建议 USD 5.00，必须先取得可靠的两模型单价/缓存计费规则及用户新的明确授权；无法估算时禁止启动，执行中费用未知即停止，不沿用上一轮“接受费用未知”。本文件只提出预算，不代表费用授权。

主指标：原 strict_success 的配对结果，单列 Patch parser/validation 参数失败、成功 Preview 后显式 Commit 成功率、Controller verified、Hidden Pass、各类安全拒绝/取消/预算耗尽/execution_uncertain。所有已分配 Attempt 都进总体分母；单独给出成功 Preview 子分母，禁止把提前停止解释为节费。计数逻辑/物理/真实 HTTP/Token/费用与审批 nonce，每次真实 yes 仅对应当前已审查命令。未知参数意图继续 unknown/null。

最大风险：远端 Schema 不兼容或模型误用 Receipt；上下文裁剪/TTL 导致额外安全拒绝；保护收紧造成完成率下降。8 对只能探索，未做功效保证。即使样本结果改善，也不直接推广到长期生产总体成功率。完成远端配置核查、费用授权和预注册冻结后，才能在另一任务启动 Live。
