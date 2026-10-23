# 下一轮真实UAT工程准备

离线工程前提已补齐；实际下一批须在其真实服务身份、真实独立Fixture和冻结配置上先运行check_environment并PASS，不能用本轮临时目录的PASS代替。新预注册须声明Fixture v2、工作区、补丁合同、摘要预算、预期断言、Task/Workflow分离及单独物理请求总额度。

优先三个新场景：单文件Preview→Receipt→Commit→Agent unittest→当前Revision verified；跨文件入口集成和真实发布/当前Revision验证；长对话真实语义摘要成功应用与关键约束/未知项保真（含空间不足零摘要请求）。后续才评估需求来源、代码解释一致性及GLM恢复。

本轮不执行这些Live，不宣称真实能力已通过。旧U04/U05/U06没有重跑、替换结果或重判。新批次开始前需要独立用户授权额度；旧22次余额封存不使用。若Fixture/Seatbelt/入口/初始Bug不合规，则在冻结前BLOCKED，不能通过放宽安全条件进入Live。

命令以macOS/zsh、Python3.12+、uv为准；本轮报告及可复现离线脚本集中在本目录与scripts/check_*。这次不是Phase26，没有归档新Tag或ZIP。
