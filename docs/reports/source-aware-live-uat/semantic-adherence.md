# Semantic adherence — LIVE BLOCKED

没有获得GRANTED_10_REQUESTS，三Case没有任何真实回复。不能说明DeepSeek正确使用已保留事实，也不能判断助手建议是否被升格、同category是否被模型误认为冲突。Mock回答只测试协议/来源路径，未被当成语义得分。

冻结标准在preregistration.md/json：S01新命名和5要求（导入时间及时区两部分）；S02无active命名、正确历史回顾、3其他要求和建议来源；S03两兼容约束、CLI仅可选、全文搜索未决。普通语义失败将按原标准记FAIL，不追问、不改提示求PASS。

请求有原事实而回答漏项，归模型使用问题；请求没有原事实，归来源投影/预算/协议问题。回答正确不能倒推请求来源完整。语义改写和因果影响证据不足用UNKNOWN。物理遗忘不是本轮成功标准。
