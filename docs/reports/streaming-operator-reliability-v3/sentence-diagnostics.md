# 格式诊断，不是语义Judge

新模块scripts/streaming_steer_recovery_v3/sentence_diagnostics.py不改写模型回复或TaskContract，也不影响生产AgentLoop。中文。！？及英文.!?分别识别，相邻中文句子不依赖后续空白；标点簇按一个结束边界处理。数字小数点不作为句末；已知缩写与复杂Markdown/代码/引号/省略号返回FORMAT_REVIEW_REQUIRED，确定性计数仅作提示。

分开deterministic_sentence_count、format_check、independent_semantic_review。可判格式不匹配，不可推出建议遵从、来源确认或语义正确；无法处理所有自然语言歧义。冒号前言不被伪计为完整句，但不会删掉状态说明句来制造两句。

旧T01公开结构的合成复现：一句执行状态说明+冒号前言+两句用途，总数3、期望2、格式FAIL。原T01 Semantic Adherence FAIL和旧观察器数字2原样保留；新模块不会倒填旧报告。样本覆盖中文/英文/混合/空白/Markdown标题/代码/列表/小数/缩写/省略号/引号/冒号/状态句。输出不是通用语义验证器。
