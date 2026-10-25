# 模型上下文、压缩和预算

持久历史不受最近6轮deque淘汰影响；查看可翻页，不表示全部历史自动进入下一请求。恢复只取有界安全user/assistant文本；失败/未结束工具不构造tool result，不恢复执行证据。近期完整工具协议仍按原Session/ContextManager处理。

请求顺序遵循原协议：system → user角色的有来源Pin参考 → 较早摘要（如有）→ 最近完整轮次 → 当前Plan状态和当前用户/工具轮。不会在assistant tool_calls与tool结果之间插Pin；不把Pin放进System。来源文本不能扩大文件、命令、MCP审批或恢复Controller Revision。

ContextManager最多试排12项，使用实际request副本、工具Schema、当前system/user、输出reserve和provider window。legacy_chars依然检查字符预算；有Pin时还检查已配置窗口；estimate_tokens用原TokenCounter。未进入预算的ID出现在pins_omitted，进入的在pins_included，Web显示逐项结果和缺失警告，CLI显示PIN警示。当前受保护输入本身超预算则停止，不请求模型；不能为了Pin突破原硬预算。

Pin优先于可裁剪旧历史；不是无条件必达。尤其大schema/当前请求可能导致所有Pin省略，不能宣称关键要求永不丢失。context.enabled=false时Pin仍计入其配置预算，避免无限附加。Pin数量/字节/历史均有限。

压缩只操作投影；ContextCompactor来源校验、TokenCounter和RuntimeAccounting原实现未改。语义摘要插入位置跳过Pin消息，不能替换/删除Pin；失败保持Pin。摘要不会生成永久Pin。撤销/替换文本所在历史轮次在摘要前整体省略，避免通过摘要返回；含未过滤语义改写仍是已知限制。

Pin操作、投影和生命周期记录增加真实模型请求数为0。已有可选语义摘要仍受原显式开关、请求次数、时间和Failover总预算控制；本轮真实语义摘要为0。SyntheticClient读取**实际提交messages**中的Pin，验证角色、有效集合和裁剪结果，不把UI展示等同于请求证据。合成机制通过不证明真实长对话任务成功率或费用改善。
