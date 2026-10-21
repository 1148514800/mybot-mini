# AI_HANDOFF

## 当前状态

独立 `codex/provider-failover-acceptance` 分支从远程smoke基线ef92f34（原实现d07f64d）完成验收。
原Phase25冻结工作区、Campaign/CSV blocked证据、main、历史Tag/ZIP和用户修改不动；1115项保护文件SHA一致。
本轮只创建本地验收提交，不Push/Merge、不进入Phase26、不新归档。

## 本轮修复

只改smoke脚本、专项、check_phase及文档；生产CLI/AgentLoop/Controller/审批/Seatbelt/单模型评测不改。
修复自然回退把2次物理请求误报1次；加入发送前HTTP计数和每probe两次硬上限。
统一外围与主预留超时，保留失败阶段、次数及关闭回执；不保存正文、原异常、Key或Patch。
保留原5项smoke，新增8项；SDK实际合成传输检查主备用自己的Key/模型、上下文和Sticky。

## 验证

专项17/17、smoke13/13、默认离线入口17/17；全量1021/1021、28套件及Phase1/2断言通过。
compileall、diff及凭证扫描通过。真实API A/B均PASS，共3/4次授权发送尝试：
A本地注入1次、主真实0、备用glm-5.3-flash真实2，Sticky成功；B主deepseek-v4.1-flash真实1正常返回，备用0。
没有自然故障、重跑、额外付费Benchmark、CLI审批提示或人工yes输入；两probe关闭确认。
费用unknown/null，Token50；不等于免费或编码质量提升。

## 配置与证据

配置是已有工作区安全复制的忽略文件，权限0600；主备用模型和凭证已校验，不提交/回显Key，测试不写回。
完整中文报告：docs/reports/provider-failover-smoke/acceptance-report.md。
脱敏JSON含离线统计、Live started/result及汇总；真实报告counting_method=http_request_hook。
全量原始日志在/tmp/provider-acceptance-full.log，未提交；报告保留日志SHA。
测试时HEAD=ef92f34加本轮修复，Live确切脚本SHA在started证据；最终提交SHA见Git。

## 下一步与限制

本次验收PASS，具备另获授权后接入独立新版本Harness的工程条件。
不自动继续旧单模型Campaign，不移除其blocked状态，不把混合模型并入旧DeepSeek组。
真实取消、备用故障、长期稳定性及编码任务质量未新增Live验证；只有离线合成证据。
不能重复付费probe补用剩余1次额度。Git仍有AppleDouble pack索引错误，未删除或修复。
