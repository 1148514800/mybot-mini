# D01 trigger path and limits

历史输入为72e5ef74fb574dc9212fca188112ef058e4762e1；原D01保持Protocol FAIL、1/1、Case failed/HALT与原账本不变。本轮不打开其私有SQLite、原始回复或旧冻结资产。

公开结构证据：Chunk221，stop观察一次，content长度0、tool_calls数量0、accepted finish=null；固定错误码stream_after_finish_payload。冻结旧实现只有`get(delta,'function_call') or (finish is not None and (content or parts))`能在该阶段产生此码。结合accepted finish与唯一terminal counter，可确认代码可达性指向legacy字段真值分支；不能把码名直接翻译为“终态后又输出正文”。

终态counter在校验前增加，但accepted finish在校验后赋值，因此observer见stop而consumer仍finish=null。该分支抛协议错误后停止迭代，未请求到自然StopAsyncIteration，随后finally先关闭独立iterator再关闭SDK owner。因此eof=false与SDK close=true可同时成立；不证明远端网络断流。

旧ring没记录function_call结构，原始Chunk按合同未存，无法恢复实际值。它可能为空SDK对象，也可能非空、含未知数据或非法类型；当前证据不区分。新Synthetic Fixture只证明一种可重现机制，不是D01原Chunk重放；不能据此宣布真实Provider根因已完全还原或改变原R01/D01评分。
