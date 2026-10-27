# Case results — offline only

|Case|Live|Mock机制验收|真实仍未知|
|---|---|---|---|
|T01|max4，未执行|SDK真实解析碎片工具、queued→admitted、旧调用配对executed=false、后续HTTP携带source reference、真实本地Read工具结果、最终合成两句|DeepSeek是否生成合适工具/下一步、是否遵从顺序/两句话|
|T02|max1，未执行|无下一步not_applied，UI提示/刷新不重发|真实短流时序窗口能否满足|
|T03|max1，未执行|真实SDK Mock流Stop/close、部分不可信、Usage null，无自动请求|真实Provider取消与费用/关闭表现|

所有Live维度BLOCKED/NOT_RUN，不能把Mock的已知合成回复当成DeepSeek语义PASS。真实普通语义失败如无安全HALT，仍允许按预注册继续下Case，不补跑。
