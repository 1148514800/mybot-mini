# Requirement Evidence

|等级|宿主状态|含义与不能推导的结论|
|---|---|---|
|0|identified / unverified / blocked|已识别或来源/执行未确证，没有需求验收证据|
|1|implementation_claimed|模型登记实现声明，不能视为成功|
|2|test_evidence_observed|模型声明关联的 test-N 确实被原 Controller 接纳为当前 Revision 测试；关联意图来自模型，不能证明覆盖此需求|
|3|independently_verified|宿主独立执行一个可信需求断言，前后 Revision/已跟踪文件哈希有效，且来源可信；正常生产没有安装此 Oracle|

observe_test 不再次运行测试、不采信单元测试名称/终端文字来自任意工具、不自动将所有要求与测试关联。Controller 原始原生命令识别与真实性检查保持不变；本层只读取其结果。链接必须引用已经观察的 test-N，不能自行提交 exit_code/执行成功。旧测试记录保持可审计，但当前 Revision 或哈希改变、Undo、取消、不确定结果会使有效证据失效。独立断言失败/异常不会写入成功记录；再次检查先撤销旧成功，不泄漏断言函数/隐藏内容或可读 Oracle 名称给 Agent，只暴露不透明引用。

Workflow Success、Revision Verified、Requirement Evidence、Task Correctness 分开。Revision verified 仍仅表示已提交修改及当前指定测试通过；合同缺少验收不会将其改判 failed。合同覆盖只按可信明确需求的独立断言计算；缺少合同、任意可信要求无独立断言均 unknown。即使已登记条目全部有断言，Task Correctness 仍 unknown，因为不能证明模型提取了全部用户需求。建议和未解决事项不算用户硬性要求。

合成 B：修复 core.py 使 service.handle(3)=6，公开 unittest 真实通过；另一个用户要求 handle(None)=[] 未覆盖，独立操作员子进程断言真实失败。Controller 仍 verified；合同 R1 Level2、R2 Level0、独立覆盖 unknown、Task Correctness unknown。没有给 Agent 提供隐藏断言，也未把操作员检查记为 Agent 自测。

本层减少的是界面将证据层级混同的机会；没有测量真实模型错误成功声明率，不据此宣称 Live 任务质量提高。工具可能增加交互/Token成本（合成 A/B各6请求），但没有固定额外的抽取/评价模型请求或无界补救；全部调用受现有预算。
