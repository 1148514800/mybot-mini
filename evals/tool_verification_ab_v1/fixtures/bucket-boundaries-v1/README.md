修复bucket(value, thresholds)：返回小于等于value的阈值数量。value必须为真正int（bool无效），可为负。thresholds仅限list或tuple，元素必须为真正int，必须严格递增且无重复，空序列合法。不满足任一输入约束抛ValueError；不修改输入。

python -m unittest discover -s tests -v
