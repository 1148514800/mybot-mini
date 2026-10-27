# Tool Call contract

实际SDK片段由原streaming.consume组装并验证完整JSON、连续索引、ID/name/参数边界、合法终态、EOF和close。UAT只原样yield，不插入/改写/补全Tool Call。T01只有原生read_file/list_files；无写入、命令、MCP/Coding权限。T02/T03无工具。

Steer在工具执行前已排队，原AgentLoop为尚未执行调用追加Error:not_executed_pending_user_steer和metadata.executed=false，保持assistant调用与tool结果配对后才到下一请求。新的观察器读取该真实SDK消息，在内存检查、只输出hash/配对/跳过布尔。按照assistant批次关联工具结果，重复结果不能重用旧配对，跨批次同ID可用消息索引区分；不改变生产协议。

真实工具started/finished事件另记许可工具枚举、call ID hash、成功布尔与受控Fixture分类。没有事件不能声称执行；已有事件也不能称为跳过。首次SDK请求不得预含RIVER标识，后续真实工具结果与最终回答的标识关系分别核验。Fixture分类不替代工具参数或任意路径导出。参数只在内存分类后丢弃，报告只有hash。
