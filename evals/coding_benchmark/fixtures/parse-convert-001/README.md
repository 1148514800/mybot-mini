# parse-convert-001

修复key:value加载链：只按第一个冒号分割、strip键值、拒绝空键；有符号十进制整数转换为int，其他值保持文本；重复键后者覆盖。

Run: python -m unittest discover -s tests -v

修改范围：仅修改已有app/下非__init__.py生产模块；不增删文件，不修改测试、README、notes或包初始化文件。运行公开unittest验证。
