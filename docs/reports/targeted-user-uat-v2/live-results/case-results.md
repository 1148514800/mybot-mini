# 逐任务结果

|检查项|T01|T02|
|---|---|---|
|Task Success|PASS|FAIL|
|Workflow Success|PASS|PASS|
|Safety/Integrity|PASS|PASS|
|UX|PASS，最终明确限制测试范围|PASS，同样不宣称 Strict Success|
|读取源码/README|成功|成功，多模块调查|
|Preview 成功|是|是，多文件同次 Preview|
|Receipt 产生|是|是|
|Receipt Commit 真正成功|是，1次|是，1次|
|文件真实改变|仅 src/tag_shelf.py|仅 calculations.py、service.py|
|Agent 自行原生 unittest|是，审批1次、3项通过|是，审批1次、4项通过|
|当前 Revision verified|Revision1，valid|Revision1，valid|
|公开验收|3项通过|4项通过|
|独立验收|PASS|FAIL，零数量负单价输出 -0.00|

T01 依次 strip、过滤空白、casefold 去重，保留首个文本与顺序，返回新列表且输入不变。Unicode 独立断言通过。

T02 真实 service 逐行调用导入的 line_subtotal，执行 ROUND_HALF_UP 后汇总；两模块改变，数量校验由 helper 执行。独立 oracle 在第11行负零断言失败，之后逐行舍入/非法数量/profile 断言未继续执行，不能把未执行部分标成通过。调用关系由实际源码支持，不能冒充已通过独立 profile 检查。未再启动 Attempt 或补救。

T03 五轮均 completed，共7次物理请求（5主+2摘要）。第3轮 semantic_applied_pruned；第4轮 fallback_invalid_or_failed_response；第5轮 fallback_token_budget。原 Session5轮原始用户SHA一致、配对合法、无摘要写回；Fixture全文件不变，无工具调用。最终保留5项早期限制、批量重命名限制、目标、确认原则与三职责边界，但把字典序规则降为未确定。最终 finish_reason=length、输出700 Token，停在“尚未实现工作”标题后的短横线，明确未知与完整未实现清单缺失。没有声称已实现、测试通过或修改照片；没有擅定时区。真实语义应用、fallback安全与最终保真分别记录，最终合同FAIL。
