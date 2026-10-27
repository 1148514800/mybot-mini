# Actual rejection and diagnostic limits

221块真实SDK Chunk，ring仅保留214–221共8块结构。拒绝点：221；phase/origin=protocol_validation；code=stream_after_finish_payload；status=provider_error。当前块choices1、delta存在、role存在、content是长度0字符串、tool_calls为0项，finish_reason=stop。全流terminal_count=1，consumer accepted finish=null；自然EOF=false，close_called=true、closed=true、terminal_trusted=false。

原streaming.py的同一个拒绝判断为`get(delta, 'function_call') or (finish is not None and (content or parts))`。错误码名称覆盖两种情形。counter在校验前累加，finish在校验后才赋值，因此stop被观察到不代表被接受。结合counter1、accepted finish null及当前空content/0tool，不支持宣称“此前已接受stop，后来又有正文”。在冻结代码路径下，代码可达性推断指向legacy function_call的真值判断。

这是源码与结构证据的推断，不是原始字段直接证据。ring没有function_call_present/type/字段是否为空等信息；原始Chunk按合同未保存，不能倒填对象内容。SDK的对象/默认值转换与部署输出各自作用仍UNKNOWN，不能直接判定部署不合规或本地验证过严。未为兼容删除include_usage、改非流式或修改源代码。

SafePreview此前释放过文本，随后consumer拒绝并提前停止迭代，SDK owner关闭。此处未观察自然EOF；不推断远端实际是否还会发[DONE]，更不能由本地停止消费推断Provider网络断流。原R01没有相同字段的直接证据，不能据此改判其原因。

供应商Usage数值在拒绝前由透明observer取得，原consumer捕获协议错误后清除可信Usage，wrapper在eof=false时也把ledger结算设null。因此observed字段齐全和ledger全null可以同时成立；无额外请求验证Usage。未来诊断应先用离线合成补充legacy字段安全结构和错误分类，新的真实样本必须另有授权与批次。
